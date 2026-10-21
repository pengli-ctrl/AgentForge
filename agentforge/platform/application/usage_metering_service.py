"""用量计量服务模块。"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from agentforge.platform.application.saas_plans import PlanCatalog, PlanDefinition
from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.risk import RiskLevel
from agentforge.platform.domain.tenant_account import TenantAccount, TenantStatus
from agentforge.platform.domain.usage import (
    InvoiceLine,
    TenantInvoice,
    UsageAlert,
    UsageDecision,
    UsageMetric,
    UsageRecord,
)
from agentforge.platform.sdk.ports import AuditPort, OutboxPort

logger = logging.getLogger(__name__)


class UsageRepository(Protocol):
    """用量仓储，负责持久化读写。"""

    async def add(self, record: UsageRecord) -> bool:
        """保存用量。

        Args:
            record: 待处理的领域记录。

        Returns:
            操作是否成功。
        """
        ...

    async def total(
        self,
        tenant_id: str,
        metric: UsageMetric,
        *,
        start: datetime,
        end: datetime,
    ) -> int:
        """统计用量。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            metric: 用量指标。
            start: 统计或查询周期的开始时间。
            end: 统计或查询周期的结束时间。

        Returns:
            整数结果。
        """
        ...

    async def list(
        self,
        tenant_id: str,
        *,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> list[UsageRecord]:
        """查询用量。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            start: 统计或查询周期的开始时间。
            end: 统计或查询周期的结束时间。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...

    async def totals(
        self,
        tenant_id: str,
        *,
        start: datetime,
        end: datetime,
    ) -> dict[UsageMetric, int]:
        """按指标汇总用量。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            start: 统计或查询周期的开始时间。
            end: 统计或查询周期的结束时间。

        Returns:
            结构化结果字典。
        """
        ...


class BillingAdapterPort(Protocol):
    """账单能力端口协议。"""

    async def create_invoice(
        self,
        account: TenantAccount,
        plan: PlanDefinition,
        totals: dict[UsageMetric, int],
        *,
        period_start: datetime,
        period_end: datetime,
    ) -> TenantInvoice:
        """创建发票。

        Args:
            account: 租户账户。
            plan: 套餐定义。
            totals: 按指标汇总的用量。
            period_start: 账单周期开始时间。
            period_end: 账单周期结束时间。

        Returns:
            租户发票结果。
        """
        ...


class UsageMeteringAdapter:
    """用量计量集成适配器。"""

    def __init__(self, service: "UsageMeteringService") -> None:
        """初始化 UsageMeteringAdapter。

        Args:
            service: 服务。
        """
        self._service = service

    async def record(
        self,
        *,
        tenant_id: str,
        metric: UsageMetric,
        quantity: int,
        source: str,
        idempotency_key: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """记录用量计量。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            metric: 用量指标。
            quantity: 本次记录的用量数量。
            source: 调用或事件来源。
            idempotency_key: 幂等键，用于避免重复处理。
            metadata: 附加元数据。
        """
        try:
            await self._service.record(
                tenant_id=tenant_id,
                metric=metric,
                quantity=quantity,
                source=source,
                idempotency_key=idempotency_key,
                metadata=dict(metadata or {}),
            )
        except ValueError as exc:
            logger.warning(
                "usage not recorded for tenant=%s metric=%s: %s",
                tenant_id,
                metric.value,
                exc,
            )


class ConfigBillingAdapter:
    """账单集成适配器。"""

    async def create_invoice(
        self,
        account: TenantAccount,
        plan: PlanDefinition,
        totals: dict[UsageMetric, int],
        *,
        period_start: datetime,
        period_end: datetime,
    ) -> TenantInvoice:
        """创建发票。

        Args:
            account: 租户账户。
            plan: 套餐定义。
            totals: 按指标汇总的用量。
            period_start: 账单周期开始时间。
            period_end: 账单周期结束时间。

        Returns:
            租户发票结果。
        """
        lines: list[InvoiceLine] = []
        for metric, quantity in totals.items():
            if quantity <= 0:
                continue
            unit_price = float(plan.unit_prices_cents.get(metric, 0.0))
            lines.append(
                InvoiceLine(
                    metric=metric,
                    quantity=quantity,
                    unit_price_cents=unit_price,
                    amount_cents=round(quantity * unit_price),
                )
            )
        return TenantInvoice(
            tenant_id=account.tenant_id,
            plan_name=plan.name,
            period_start=period_start,
            period_end=period_end,
            base_fee_cents=plan.base_fee_cents,
            lines=lines,
            total_cents=plan.base_fee_cents + sum(line.amount_cents for line in lines),
        )


class UsageMeteringService:
    """用量计量应用服务，编排领域用例及其副作用。"""

    def __init__(
        self,
        repository: UsageRepository,
        account_repository,
        plan_catalog: PlanCatalog,
        *,
        audit: AuditPort | None = None,
        outbox: OutboxPort | None = None,
        billing: BillingAdapterPort | None = None,
    ) -> None:
        """初始化 UsageMeteringService。

        Args:
            repository: 数据仓储实现。
            account_repository: 仓储。
            plan_catalog: 套餐目录。
            audit: 审计。
            outbox: Outbox。
            billing: 账单适配器。
        """
        self._repository = repository
        self._accounts = account_repository
        self._plans = plan_catalog
        self._audit = audit
        self._outbox = outbox
        self._billing = billing or ConfigBillingAdapter()

    async def record(
        self,
        *,
        tenant_id: str,
        metric: UsageMetric,
        quantity: int,
        source: str = "platform",
        idempotency_key: str = "",
        occurred_at: datetime | None = None,
        metadata: dict | None = None,
    ) -> UsageDecision:
        """记录用量计量。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            metric: 用量指标。
            quantity: 本次记录的用量数量。
            source: 调用或事件来源。
            idempotency_key: 幂等键，用于避免重复处理。
            occurred_at: 用量发生时间。
            metadata: 附加元数据。

        Returns:
            用量决策结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if quantity <= 0:
            raise ValueError("usage quantity must be positive")
        account = await self._require_account(tenant_id)
        if account.status != TenantStatus.ACTIVE:
            raise ValueError(f"tenant is not active: {account.status.value}")
        plan = self._plans.get(account.plan_name)
        timestamp = occurred_at or datetime.now(timezone.utc)
        start, end = _month_period(timestamp)
        used = await self._repository.total(tenant_id, metric, start=start, end=end)
        limit = plan.limit_for(metric)
        overage = max(0, used + quantity - limit) if limit > 0 else 0
        if limit > 0 and used + quantity > limit and plan.overage_policy == "block":
            decision = UsageDecision(
                accepted=False,
                blocked=True,
                metric=metric,
                used=used,
                limit=limit,
                overage=overage,
                policy=plan.overage_policy,
            )
            await self._record_overage(account, decision, source)
            return decision
        record = UsageRecord(
            tenant_id=tenant_id,
            metric=metric,
            quantity=quantity,
            source=source.strip() or "platform",
            idempotency_key=idempotency_key.strip() or str(uuid4()),
            occurred_at=timestamp,
            metadata=dict(metadata or {}),
        )
        added = await self._repository.add(record)
        decision = UsageDecision(
            accepted=True,
            blocked=False,
            metric=metric,
            used=used + (quantity if added else 0),
            limit=limit,
            overage=overage if added else max(0, used - limit) if limit > 0 else 0,
            policy=plan.overage_policy,
            record_id=record.record_id,
            duplicate=not added,
        )
        if added and overage > 0:
            await self._record_overage(account, decision, source)
        return decision

    async def summary(
        self,
        tenant_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        """汇总用量计量信息。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            start: 统计或查询周期的开始时间。
            end: 统计或查询周期的结束时间。

        Returns:
            结构化结果字典。
        """
        account = await self._require_account(tenant_id)
        plan = self._plans.get(account.plan_name)
        start, end = _normalize_period(start, end)
        totals = await self._repository.totals(tenant_id, start=start, end=end)
        metrics = {}
        for metric in UsageMetric:
            used = totals.get(metric, 0)
            limit = plan.limit_for(metric)
            metrics[metric.value] = {
                "used": used,
                "limit": limit,
                "unlimited": limit == 0,
                "ratio": round(used / limit, 4) if limit > 0 else 0.0,
                "overage": max(0, used - limit) if limit > 0 else 0,
            }
        return {
            "tenant_id": tenant_id,
            "plan_name": plan.name,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "automation_quota": plan.automation_quota,
            "overage_policy": plan.overage_policy,
            "metrics": metrics,
        }

    async def alerts(
        self,
        tenant_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[UsageAlert]:
        """查询用量计量告警。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            start: 统计或查询周期的开始时间。
            end: 统计或查询周期的结束时间。

        Returns:
            结果列表。
        """
        summary = await self.summary(tenant_id, start=start, end=end)
        result: list[UsageAlert] = []
        for metric_name, values in summary["metrics"].items():
            limit = int(values["limit"])
            used = int(values["used"])
            if limit <= 0:
                continue
            ratio = used / limit
            if ratio >= 1:
                status = "critical"
            elif ratio >= 0.8:
                status = "warning"
            else:
                continue
            result.append(
                UsageAlert(
                    tenant_id=tenant_id,
                    metric=UsageMetric(metric_name),
                    status=status,
                    used=used,
                    limit=limit,
                    ratio=round(ratio, 4),
                )
            )
        return result

    async def invoice(
        self,
        tenant_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> TenantInvoice:
        """执行发票。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            start: 统计或查询周期的开始时间。
            end: 统计或查询周期的结束时间。

        Returns:
            租户发票结果。
        """
        account = await self._require_account(tenant_id)
        plan = self._plans.get(account.plan_name)
        start, end = _normalize_period(start, end)
        totals = await self._repository.totals(tenant_id, start=start, end=end)
        return await self._billing.create_invoice(
            account,
            plan,
            totals,
            period_start=start,
            period_end=end,
        )

    async def _require_account(self, tenant_id: str) -> TenantAccount:
        """执行校验账户。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            租户结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        account = await self._accounts.get(tenant_id)
        if account is None:
            raise ValueError(f"tenant not found: {tenant_id}")
        return account

    async def _record_overage(
        self,
        account: TenantAccount,
        decision: UsageDecision,
        source: str,
    ) -> None:
        """记录用量。

        Args:
            account: 租户账户。
            decision: 待处理的授权或审批决策。
            source: 调用或事件来源。
        """
        trace_id = str(uuid4())
        payload = {
            "metric": decision.metric.value,
            "used": decision.used,
            "limit": decision.limit,
            "overage": decision.overage,
            "policy": decision.policy,
            "source": source,
            "blocked": decision.blocked,
        }
        if self._audit is not None:
            await self._audit.save(
                AuditEvent(
                    event_id=str(uuid4()),
                    tenant_id=account.tenant_id,
                    action="tenant.usage.blocked" if decision.blocked else "tenant.usage.overage",
                    resource_type="tenant_usage",
                    resource_id=decision.metric.value,
                    risk_level=RiskLevel.HIGH,
                    actor_type="system",
                    actor_id="usage-meter",
                    trace_id=trace_id,
                    payload=payload,
                )
            )
        if self._outbox is not None:
            await self._outbox.enqueue(
                EventEnvelope(
                    event_id=str(uuid4()),
                    event_type="platform.tenant.usage.overage.v1",
                    tenant_id=account.tenant_id,
                    task_id=decision.metric.value,
                    trace_id=trace_id,
                    producer="usage-meter",
                    payload=payload,
                )
            )


def _month_period(value: datetime) -> tuple[datetime, datetime]:
    """处理周期。

    Args:
        value: 待处理值。

    Returns:
        结果元组。
    """
    start = value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _normalize_period(
    start: datetime | None,
    end: datetime | None,
) -> tuple[datetime, datetime]:
    """规范化周期。

    Args:
        start: 统计或查询周期的开始时间。
        end: 统计或查询周期的结束时间。

    Returns:
        结果元组。

    Raises:
        ValueError: 输入值或业务状态不合法时抛出。
    """
    current = datetime.now(timezone.utc)
    default_start, default_end = _month_period(current)
    resolved_start = start or default_start
    resolved_end = end or default_end
    if resolved_start.tzinfo is None:
        resolved_start = resolved_start.replace(tzinfo=timezone.utc)
    if resolved_end.tzinfo is None:
        resolved_end = resolved_end.replace(tzinfo=timezone.utc)
    if resolved_start >= resolved_end:
        raise ValueError("period start must be before end")
    return resolved_start, resolved_end


__all__ = [
    "BillingAdapterPort",
    "ConfigBillingAdapter",
    "UsageMeteringService",
    "UsageMeteringAdapter",
    "UsageRepository",
]
