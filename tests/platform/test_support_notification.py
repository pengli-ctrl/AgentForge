"""测试客服通知测试模块。"""

from __future__ import annotations

import pytest

from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.modules.support.application.notification import SupportNotificationService
from agentforge.platform.modules.support.domain.ticket import Ticket, TicketStatus
from agentforge.platform.modules.support.infrastructure.memory_notification_gateway import (
    MemoryNotificationGateway,
)
from agentforge.platform.modules.support.infrastructure.memory_repository import (
    MemoryTicketRepository,
)
from agentforge.platform.modules.support.infrastructure.webhook_notification_gateway import (
    WebhookNotificationGateway,
)


@pytest.mark.asyncio
async def test_sla_notification_service_delivers_once_and_records_evidence() -> None:
    """验证SLA通知服务一次及记录证据对应的测试场景。"""
    repository = MemoryTicketRepository()
    gateway = MemoryNotificationGateway()
    service = SupportNotificationService(gateway, repository)
    ticket = Ticket(
        ticket_id="ticket-notify",
        tenant_id="tenant-notify",
        source="expense-invoice-gate",
        subject="Invoice gate alert stale block",
        status=TicketStatus.WAITING_REVIEW,
        assigned_team="finance-control",
        assignee_id="finance-bot",
        idempotency_key="notify-1",
        metadata={"notification_target": "chat-finance"},
    )
    await repository.save(ticket)
    event = EventEnvelope(
        event_id="event-notify-1",
        event_type="support.ticket.sla_due_soon.v1",
        tenant_id="tenant-notify",
        task_id="ticket-notify",
        trace_id="trace-notify-1",
        producer="support-sla-sweeper",
        payload={
            "ticket_id": "ticket-notify",
            "priority": "p2",
            "assignee_id": "finance-bot",
            "due_at": "2026-10-21T10:00:00+00:00",
            "notification_target": "chat-finance",
        },
    )

    await service.handle_sla_event(event)
    await service.handle_sla_event(event)

    stored = await repository.get("tenant-notify", "ticket-notify")
    assert len(gateway.sent) == 1
    assert gateway.sent[0]["target"] == "chat-finance"
    assert "finance-bot" in str(gateway.sent[0]["text"])
    assert stored is not None
    assert len(stored.metadata["notifications"]) == 1
    assert stored.metadata["notifications"][0]["event_id"] == "event-notify-1"


@pytest.mark.asyncio
async def test_webhook_notification_gateway_sends_idempotency_headers() -> None:
    """验证Webhook通知网关发送对应的测试场景。"""
    requests: list[dict] = []

    class Response:
        """响应相关组件。"""

        status_code = 202

    async def request(method: str, url: str, **kwargs):
        """处理请求。

        Args:
            method: HTTP 或业务方法名。
            url: 目标 URL。
            kwargs: 关键字参数。

        Returns:
            处理结果。
        """
        requests.append({"method": method, "url": url, **kwargs})
        return Response()

    gateway = WebhookNotificationGateway(
        "https://hooks.example.com/agentforge",
        token="secret-token",
        request_fn=request,
    )
    result = await gateway.send(
        tenant_id="tenant-notify",
        ticket_id="ticket-notify",
        event_type="support.ticket.sla_breached.v1",
        idempotency_key="event-notify-2",
        text="SLA breached",
        payload={"ticket_id": "ticket-notify"},
        target="finance-room",
    )

    assert result["delivered"] is True
    assert requests[0]["headers"]["X-Idempotency-Key"] == "event-notify-2"
    assert requests[0]["headers"]["Authorization"] == "Bearer secret-token"
    assert requests[0]["json"]["target"] == "finance-room"
