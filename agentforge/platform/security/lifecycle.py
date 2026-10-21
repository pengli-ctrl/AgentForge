"""生命周期模块。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.risk import RiskLevel
from agentforge.platform.sdk.ports import AuditPort, OutboxPort

TenantDataEraser = Callable[[str], Awaitable[dict[str, int]]]


class DataLifecycleError(ValueError):
    """数据生命周期错误相关组件。"""


class TenantDataLifecycleService:
    """租户数据生命周期应用服务，编排领域用例及其副作用。"""

    def __init__(self, audit: AuditPort, outbox: OutboxPort | None = None) -> None:
        """初始化 TenantDataLifecycleService。

        Args:
            audit: 审计。
            outbox: Outbox。
        """
        self._audit = audit
        self._outbox = outbox
        self._erasers: dict[str, TenantDataEraser] = {}

    def register_eraser(self, owner: str, eraser: TenantDataEraser) -> None:
        """注册租户数据生命周期。

        Args:
            owner: 输入参数。
            eraser: 输入参数。

        Raises:
            DataLifecycleError: 操作无法完成时抛出。
        """
        if not owner.strip() or not callable(eraser):
            raise DataLifecycleError("eraser owner and callable are required")
        self._erasers[owner.strip()] = eraser

    async def erase_tenant(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        reason: str,
        confirmation: str,
    ) -> dict[str, Any]:
        """擦除租户。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            actor_id: 执行操作的参与者 ID。
            reason: 变更原因。
            confirmation: 确认。

        Returns:
            结构化结果字典。

        Raises:
            DataLifecycleError: 操作无法完成时抛出。
        """
        if not tenant_id.strip() or not actor_id.strip():
            raise DataLifecycleError("tenant_id and actor_id are required")
        if confirmation != tenant_id:
            raise DataLifecycleError("confirmation must exactly match tenant_id")
        if not self._erasers:
            raise DataLifecycleError("no tenant data erasers are registered")
        summary: dict[str, int] = {}
        errors: dict[str, str] = {}
        for owner, eraser in self._erasers.items():
            try:
                result = await eraser(tenant_id)
                summary.update({f"{owner}.{key}": int(value) for key, value in result.items()})
            except Exception as exc:  # noqa: BLE001 - continue other owners, report failures
                errors[owner] = str(exc)[:500]
        trace_id = str(uuid4())
        await self._audit.save(
            AuditEvent(
                event_id=str(uuid4()),
                tenant_id=tenant_id,
                action="tenant.data.erased" if not errors else "tenant.data.erase_partial",
                resource_type="tenant_data",
                resource_id=tenant_id,
                risk_level=RiskLevel.HIGH,
                actor_type="user",
                actor_id=actor_id,
                trace_id=trace_id,
                payload={"reason": reason, "summary": summary, "errors": errors},
            )
        )
        if self._outbox is not None:
            await self._outbox.enqueue(
                EventEnvelope(
                    event_id=str(uuid4()),
                    event_type="platform.tenant.data_erased.v1",
                    tenant_id=tenant_id,
                    task_id=tenant_id,
                    trace_id=trace_id,
                    producer="tenant-data-lifecycle",
                    payload={"summary": summary, "errors": errors, "reason": reason},
                )
            )
        if errors:
            raise DataLifecycleError(f"tenant erasure incomplete: {errors}")
        return {"tenant_id": tenant_id, "erased": summary, "errors": errors}


__all__ = ["DataLifecycleError", "TenantDataEraser", "TenantDataLifecycleService"]
