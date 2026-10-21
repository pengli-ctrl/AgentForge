"""租户生命周期服务模块。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from agentforge.platform.application.saas_plans import PlanCatalog, PlanDefinition
from agentforge.platform.application.tenant_module_service import TenantModuleService
from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.risk import RiskLevel
from agentforge.platform.domain.tenant_account import TenantAccount, TenantStatus
from agentforge.platform.domain.tenant_quota import TenantQuota
from agentforge.platform.sdk.ports import AuditPort, OutboxPort


class TenantAccountRepository(Protocol):
    """租户账户仓储，负责持久化读写。"""

    async def save(self, account: TenantAccount) -> None:
        """保存租户账户。

        Args:
            account: 租户账户。
        """
        ...

    async def get(self, tenant_id: str) -> TenantAccount | None:
        """读取租户账户。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            租户无结果。
        """
        ...

    async def list(self, limit: int = 100) -> list[TenantAccount]:
        """查询租户账户。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...


class TenantLifecycleError(ValueError):
    """租户生命周期错误相关组件。"""


class TenantLifecycleService:
    """租户生命周期应用服务，编排领域用例及其副作用。"""

    def __init__(
        self,
        repository: TenantAccountRepository,
        module_service: TenantModuleService,
        plan_catalog: PlanCatalog,
        *,
        quota_repository=None,
        audit: AuditPort | None = None,
        outbox: OutboxPort | None = None,
    ) -> None:
        """初始化 TenantLifecycleService。

        Args:
            repository: 数据仓储实现。
            module_service: 模块服务。
            plan_catalog: 套餐目录。
            quota_repository: 配额仓储。
            audit: 审计。
            outbox: Outbox。
        """
        self._repository = repository
        self._module_service = module_service
        self._plans = plan_catalog
        self._quota_repository = quota_repository
        self._audit = audit
        self._outbox = outbox

    async def provision(
        self,
        *,
        tenant_id: str,
        name: str,
        plan_name: str,
        actor_id: str,
    ) -> TenantAccount:
        """开通租户生命周期。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            name: 资源或对象名称。
            plan_name: 套餐名称。
            actor_id: 执行操作的参与者 ID。

        Returns:
            租户结果。

        Raises:
            TenantLifecycleError: 操作无法完成时抛出。
            Exception: 操作无法完成时抛出。
        """
        if not tenant_id.strip() or not name.strip() or not actor_id.strip():
            raise TenantLifecycleError("tenant_id, name and actor_id are required")
        if await self._repository.get(tenant_id) is not None:
            raise TenantLifecycleError(f"tenant already exists: {tenant_id}")
        try:
            plan = self._plans.get(plan_name)
        except KeyError as exc:
            raise TenantLifecycleError(str(exc)) from exc
        now = datetime.now(timezone.utc)
        account = TenantAccount(
            tenant_id=tenant_id,
            name=name.strip(),
            plan_name=plan.name,
            status=TenantStatus.PROVISIONING,
            created_at=now,
            updated_at=now,
        )
        await self._repository.save(account)
        try:
            await self._apply_plan(account, plan, actor_id)
        except Exception:
            account.status = TenantStatus.CANCELLED
            account.status_reason = "provisioning failed"
            account.updated_at = datetime.now(timezone.utc)
            await self._repository.save(account)
            raise
        account.status = TenantStatus.ACTIVE
        account.updated_at = datetime.now(timezone.utc)
        await self._repository.save(account)
        await self._record(
            account,
            action="tenant.provisioned",
            actor_id=actor_id,
            payload={"plan_name": plan.name, "modules": list(plan.modules)},
            event_type="platform.tenant.provisioned.v1",
        )
        return account

    async def get(self, tenant_id: str) -> TenantAccount | None:
        """获取租户生命周期。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            租户无结果。
        """
        return await self._repository.get(tenant_id)

    async def list(self, limit: int = 100) -> list[TenantAccount]:
        """查询租户生命周期。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        return await self._repository.list(limit)

    async def suspend(self, tenant_id: str, *, actor_id: str, reason: str) -> TenantAccount:
        """暂停租户生命周期。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            actor_id: 执行操作的参与者 ID。
            reason: 变更原因。

        Returns:
            租户结果。

        Raises:
            TenantLifecycleError: 操作无法完成时抛出。
        """
        account = await self._require(tenant_id)
        if account.status == TenantStatus.CANCELLED:
            raise TenantLifecycleError("cancelled tenant cannot be suspended")
        account.status = TenantStatus.SUSPENDED
        account.suspended_at = datetime.now(timezone.utc)
        account.updated_at = account.suspended_at
        account.status_reason = reason.strip()
        await self._repository.save(account)
        await self._record(
            account,
            action="tenant.suspended",
            actor_id=actor_id,
            payload={"reason": account.status_reason},
            event_type="platform.tenant.suspended.v1",
        )
        return account

    async def resume(self, tenant_id: str, *, actor_id: str, reason: str = "") -> TenantAccount:
        """恢复租户生命周期。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            actor_id: 执行操作的参与者 ID。
            reason: 变更原因。

        Returns:
            租户结果。

        Raises:
            TenantLifecycleError: 操作无法完成时抛出。
        """
        account = await self._require(tenant_id)
        if account.status != TenantStatus.SUSPENDED:
            raise TenantLifecycleError("only suspended tenant can be resumed")
        account.status = TenantStatus.ACTIVE
        account.suspended_at = None
        account.updated_at = datetime.now(timezone.utc)
        account.status_reason = reason.strip()
        await self._repository.save(account)
        await self._record(
            account,
            action="tenant.resumed",
            actor_id=actor_id,
            payload={"reason": account.status_reason},
            event_type="platform.tenant.resumed.v1",
        )
        return account

    async def cancel(self, tenant_id: str, *, actor_id: str, reason: str) -> TenantAccount:
        """取消租户生命周期。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            actor_id: 执行操作的参与者 ID。
            reason: 变更原因。

        Returns:
            租户结果。
        """
        account = await self._require(tenant_id)
        account.status = TenantStatus.CANCELLED
        account.cancelled_at = datetime.now(timezone.utc)
        account.updated_at = account.cancelled_at
        account.status_reason = reason.strip()
        await self._repository.save(account)
        for module_name in self._module_service.list_registered_modules():
            await self._module_service.set_enabled(
                tenant_id=tenant_id,
                module_name=module_name,
                enabled=False,
                actor_id=actor_id,
                plan_name=account.plan_name,
            )
        await self._record(
            account,
            action="tenant.cancelled",
            actor_id=actor_id,
            payload={"reason": account.status_reason},
            event_type="platform.tenant.cancelled.v1",
        )
        return account

    async def change_plan(
        self,
        tenant_id: str,
        *,
        plan_name: str,
        actor_id: str,
    ) -> TenantAccount:
        """变更套餐。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            plan_name: 套餐名称。
            actor_id: 执行操作的参与者 ID。

        Returns:
            租户结果。

        Raises:
            TenantLifecycleError: 操作无法完成时抛出。
        """
        account = await self._require(tenant_id)
        if account.status != TenantStatus.ACTIVE:
            raise TenantLifecycleError("plan changes require an active tenant")
        try:
            plan = self._plans.get(plan_name)
        except KeyError as exc:
            raise TenantLifecycleError(str(exc)) from exc
        previous = account.plan_name
        account.plan_name = plan.name
        account.updated_at = datetime.now(timezone.utc)
        await self._apply_plan(account, plan, actor_id)
        await self._repository.save(account)
        await self._record(
            account,
            action="tenant.plan.changed",
            actor_id=actor_id,
            payload={"previous_plan": previous, "plan_name": plan.name},
            event_type="platform.tenant.plan_changed.v1",
        )
        return account

    async def _apply_plan(
        self,
        account: TenantAccount,
        plan: PlanDefinition,
        actor_id: str,
    ) -> None:
        """应用计划。

        Args:
            account: 租户账户。
            plan: 套餐定义。
            actor_id: 执行操作的参与者 ID。
        """
        plan_modules = set(plan.modules)
        for module_name in self._module_service.list_registered_modules():
            enabled = module_name in plan_modules
            await self._module_service.set_enabled(
                tenant_id=account.tenant_id,
                module_name=module_name,
                enabled=enabled,
                actor_id=actor_id,
                plan_name=plan.name,
            )
            if enabled:
                await self._module_service.set_config(
                    tenant_id=account.tenant_id,
                    module_name=module_name,
                    values=dict(plan.module_configs.get(module_name, {})),
                    actor_id=actor_id,
                    enabled=True,
                )
        if self._quota_repository is not None:
            await self._quota_repository.upsert(
                TenantQuota(
                    tenant_id=account.tenant_id,
                    monthly_limit=float(plan.automation_quota),
                    warning_threshold=0.8,
                    hard_limit=1.0,
                    enabled=plan.automation_quota > 0,
                    updated_at=datetime.now(timezone.utc),
                )
            )

    async def _require(self, tenant_id: str) -> TenantAccount:
        """执行校验。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            租户结果。

        Raises:
            TenantLifecycleError: 操作无法完成时抛出。
        """
        account = await self._repository.get(tenant_id)
        if account is None:
            raise TenantLifecycleError(f"tenant not found: {tenant_id}")
        return account

    async def _record(
        self,
        account: TenantAccount,
        *,
        action: str,
        actor_id: str,
        payload: Mapping[str, object],
        event_type: str,
    ) -> None:
        """记录租户生命周期。

        Args:
            account: 租户账户。
            action: 待执行动作名称。
            actor_id: 执行操作的参与者 ID。
            payload: 事件、工作流或请求载荷。
            event_type: 事件类型。
        """
        trace_id = str(uuid4())
        if self._audit is not None:
            await self._audit.save(
                AuditEvent(
                    event_id=str(uuid4()),
                    tenant_id=account.tenant_id,
                    action=action,
                    resource_type="tenant",
                    resource_id=account.tenant_id,
                    risk_level=RiskLevel.HIGH,
                    actor_type="user",
                    actor_id=actor_id,
                    trace_id=trace_id,
                    payload=dict(payload),
                )
            )
        if self._outbox is not None:
            await self._outbox.enqueue(
                EventEnvelope(
                    event_id=str(uuid4()),
                    event_type=event_type,
                    tenant_id=account.tenant_id,
                    task_id=account.tenant_id,
                    trace_id=trace_id,
                    producer="tenant-lifecycle",
                    payload={"status": account.status.value, **dict(payload)},
                )
            )


__all__ = ["TenantAccountRepository", "TenantLifecycleError", "TenantLifecycleService"]
