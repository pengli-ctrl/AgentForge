"""测试客服SLA测试模块。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agentforge.platform.domain.priority import PriorityLevel
from agentforge.platform.modules.support.application.classifier import RuleBasedTicketClassifier
from agentforge.platform.modules.support.application.routing import (
    SupportSlaMetricsService,
    SupportTicketPolicy,
)
from agentforge.platform.modules.support.application.service import SupportTicketService
from agentforge.platform.modules.support.domain.ticket import Ticket, TicketStatus
from agentforge.platform.modules.support.infrastructure.memory_repository import (
    MemoryTicketRepository,
)


@pytest.mark.asyncio
async def test_support_sla_metrics_report_overdue_finance_ticket() -> None:
    """验证客服SLA指标报告逾期财务工单对应的测试场景。"""
    repository = MemoryTicketRepository()
    policy = SupportTicketPolicy(invoice_gate_team="finance-control")
    now = datetime.now(timezone.utc)
    ticket = Ticket(
        ticket_id="sla-overdue",
        tenant_id="tenant-sla",
        source="expense-invoice-gate",
        subject="invoice gate alert",
        status=TicketStatus.WAITING_REVIEW,
        priority=PriorityLevel.P2,
        assigned_team="finance-control",
        idempotency_key="alert-sla",
        metadata={
            "queue": "finance-control",
            "sla": {
                "policy": "invoice-gate",
                "minutes": 45,
                "due_at": (now - timedelta(minutes=5)).isoformat(),
                "status": "open",
            },
        },
        created_at=now - timedelta(minutes=50),
        updated_at=now - timedelta(minutes=50),
    )
    await repository.save(ticket)

    metrics = await SupportSlaMetricsService(repository, policy).render_metrics()

    assert "agentforge_support_ticket_sla_open" in metrics
    assert "agentforge_support_ticket_sla_overdue" in metrics
    assert "agentforge_support_ticket_sla_oldest_open_age_seconds" in metrics
    assert 'team="finance-control"' in metrics
    assert 'priority="p2"} 1' in metrics


@pytest.mark.asyncio
async def test_support_sla_sweep_notifies_once_and_escalates_overdue() -> None:
    """验证客服SLA扫描一次及升级逾期对应的测试场景。"""
    repository = MemoryTicketRepository()
    policy = SupportTicketPolicy(
        due_soon_seconds=900,
        sla_escalation_assignee="sla-manager",
    )
    service = SupportTicketService(
        repository,
        RuleBasedTicketClassifier(),
        ticket_policy=policy,
    )
    now = datetime.now(timezone.utc)
    due_soon_ticket = Ticket(
        ticket_id="sla-due-soon",
        tenant_id="tenant-sla",
        source="expense-invoice-gate",
        status=TicketStatus.WAITING_REVIEW,
        priority=PriorityLevel.P2,
        assigned_team="finance-control",
        assignee_id="finance-bot",
        idempotency_key="sla-due-soon",
        metadata={
            "queue": "finance-control",
            "sla": {
                "due_at": (now + timedelta(minutes=5)).isoformat(),
                "status": "open",
            },
        },
    )
    overdue_ticket = Ticket(
        ticket_id="sla-overdue-sweep",
        tenant_id="tenant-sla",
        source="expense-invoice-gate",
        status=TicketStatus.WAITING_REVIEW,
        priority=PriorityLevel.P2,
        assigned_team="finance-control",
        idempotency_key="sla-overdue-sweep",
        metadata={
            "queue": "finance-control",
            "notification_target": "chat-finance",
            "sla": {
                "due_at": (now - timedelta(minutes=5)).isoformat(),
                "status": "open",
            },
        },
    )
    await repository.save(due_soon_ticket)
    await repository.save(overdue_ticket)

    first = await service.sweep_sla(now)
    second = await service.sweep_sla(now)

    assert first["due_soon"] == 1
    assert first["breached"] == 1
    assert first["escalated"] == 1
    assert second["due_soon"] == 0
    assert second["breached"] == 0
    assert second["escalated"] == 0
    stored_due_soon = await repository.get("tenant-sla", "sla-due-soon")
    stored_overdue = await repository.get("tenant-sla", "sla-overdue-sweep")
    assert stored_due_soon is not None
    assert stored_overdue is not None
    assert stored_due_soon.status == TicketStatus.WAITING_REVIEW
    assert stored_due_soon.metadata["sla"]["due_soon_notified_at"]
    assert stored_overdue.status == TicketStatus.ESCALATED
    assert stored_overdue.assignee_id == "sla-manager"
    assert stored_overdue.metadata["sla"]["escalated_to_assignee"] == "sla-manager"
    assert stored_overdue.metadata["sla"]["breach_notified_at"]
    assert stored_overdue.metadata["sla"]["escalated_at"]
    breached_event = next(
        event for event in repository.outbox if event.event_type == "support.ticket.sla_breached.v1"
    )
    assert breached_event.payload["assignee_id"] == "sla-manager"
    assert breached_event.payload["notification_target"] == "chat-finance"
    assert {event.event_type for event in repository.outbox} == {
        "support.ticket.sla_due_soon.v1",
        "support.ticket.sla_breached.v1",
    }


def test_invoice_gate_policy_assigns_owner() -> None:
    """验证发票门禁策略对应的测试场景。"""
    policy = SupportTicketPolicy(
        invoice_gate_team="finance-control",
        invoice_gate_assignee="finance-bot",
        invoice_gate_sla_minutes=45,
    )
    ticket = Ticket(
        ticket_id="sla-assignee",
        tenant_id="tenant-sla",
        source="expense-invoice-gate",
        idempotency_key="sla-assignee",
    )

    policy.apply(ticket, source="expense-invoice-gate")

    assert ticket.assigned_team == "finance-control"
    assert ticket.assignee_id == "finance-bot"
    assert ticket.metadata["sla"]["minutes"] == 45


def test_support_sla_close_records_breach() -> None:
    """验证客服SLA记录对应的测试场景。"""
    policy = SupportTicketPolicy()
    now = datetime.now(timezone.utc)
    ticket = Ticket(
        ticket_id="sla-closed",
        tenant_id="tenant-sla",
        source="expense-invoice-gate",
        idempotency_key="alert-closed",
        created_at=now - timedelta(hours=2),
        metadata={
            "sla": {
                "due_at": (now - timedelta(hours=1)).isoformat(),
                "status": "open",
            }
        },
    )

    policy.close_sla(ticket, outcome="published", closed_at=now)

    assert ticket.metadata["sla"]["status"] == "breached"
    assert "closed_at" in ticket.metadata["sla"]
