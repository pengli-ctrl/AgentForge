"""通知模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.usage import UsageMetric
from agentforge.platform.modules.support.ports import NotificationPort, TicketRepository
from agentforge.platform.sdk.ports import AuditPort, UsagePort


class SupportNotificationService:
    """客服通知应用服务，编排领域用例及其副作用。"""

    def __init__(
        self,
        gateway: NotificationPort,
        repository: TicketRepository,
        audit: AuditPort | None = None,
        usage: UsagePort | None = None,
    ) -> None:
        """初始化 SupportNotificationService。

        Args:
            gateway: 网关。
            repository: 数据仓储实现。
            audit: 审计。
            usage: 用量统计数据。
        """
        self._gateway = gateway
        self._repository = repository
        self._audit = audit
        self._usage = usage

    async def handle_sla_event(self, event: EventEnvelope) -> None:
        """处理SLA事件。

        Args:
            event: 待处理事件。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        ticket_id = str(event.payload.get("ticket_id") or "")
        if not ticket_id:
            return
        ticket = await self._repository.get(event.tenant_id, ticket_id)
        if ticket is None:
            return
        notifications = ticket.metadata.get("notifications")
        delivered = list(notifications) if isinstance(notifications, list) else []
        if any(
            isinstance(item, dict) and item.get("event_id") == event.event_id for item in delivered
        ):
            return

        target = (
            str(
                event.payload.get("notification_target")
                or ticket.metadata.get("notification_target")
                or ""
            ).strip()
            or None
        )
        result = await self._gateway.send(
            tenant_id=event.tenant_id,
            ticket_id=ticket.ticket_id,
            event_type=event.event_type,
            idempotency_key=event.event_id,
            text=_notification_text(ticket.subject, event.payload),
            payload=dict(event.payload),
            target=target,
        )
        if result.get("delivered") is not True:
            raise RuntimeError("support notification was not delivered")

        delivered_at = datetime.now(timezone.utc).isoformat()
        delivered.append(
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "target": target,
                "delivered_at": delivered_at,
                "result": result,
            }
        )
        ticket.metadata["notifications"] = delivered
        await self._repository.save(ticket)
        if self._audit is not None:
            await self._audit.save(
                AuditEvent(
                    event_id=str(uuid4()),
                    tenant_id=ticket.tenant_id,
                    action="ticket.sla_notification_sent",
                    resource_type="ticket",
                    resource_id=ticket.ticket_id,
                    risk_level=ticket.risk_level,
                    actor_type="system",
                    actor_id="support-notification-service",
                    trace_id=event.trace_id,
                    payload={
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "target": target,
                    },
                )
            )
        if self._usage is not None:
            await self._usage.record(
                tenant_id=ticket.tenant_id,
                metric=UsageMetric.NOTIFICATION_COUNT,
                quantity=1,
                source="support-notification",
                idempotency_key=f"notification:{event.event_id}",
                metadata={"event_type": event.event_type},
            )


def _notification_text(subject: str, payload: dict[str, Any]) -> str:
    """处理通知文本。

    Args:
        subject: 输入参数。
        payload: 事件、工作流或请求载荷。

    Returns:
        字符串结果。
    """
    priority = str(payload.get("priority") or "p3")
    assignee = str(payload.get("assignee_id") or "unassigned")
    due_at = str(payload.get("due_at") or "")
    return f"[{priority.upper()}] {subject or 'Support ticket'} | owner={assignee} | due={due_at}"
