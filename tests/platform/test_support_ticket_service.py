"""客服工单服务测试模块。

本测试模块验证 test_support_ticket_service 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_low_risk_event_creates_ticket_waiting_review、test_duplicate_event_returns_existing_tic
    ket、test_webhook_returns_high_risk_ticket、test_approval_api_moves_ticket_to_ready_to_publish
    、test_reply_api_publishes_approved_ticket、test_reply_api_requires_non_empty_text。
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.modules.support.domain.ticket import TicketStatus
from agentforge.platform.runtime import build_memory_container
from tests.platform.support_fixtures import configure_memory_support, create_app_with_support


@pytest.mark.asyncio
async def test_low_risk_event_creates_ticket_waiting_review() -> None:
    """验证低风险事件创建工单等待审核对应的测试场景。"""
    container = build_memory_container()
    support = configure_memory_support(container)
    event = {
        "tenant_id": "tenant-1",
        "source": "feishu",
        "message_id": "msg-1",
        "text": "How do I use this product?",
    }
    ticket = await support.ticket_service.create_from_event(event)
    assert ticket.status == TicketStatus.WAITING_REVIEW
    assert ticket.assigned_team == "support"
    assert len(support.repository.outbox) == 1


@pytest.mark.asyncio
async def test_duplicate_event_returns_existing_ticket() -> None:
    """验证重复事件返回现有工单对应的测试场景。"""
    container = build_memory_container()
    support = configure_memory_support(container)
    event = {
        "tenant_id": "tenant-1",
        "source": "feishu",
        "message_id": "msg-2",
        "text": "The product is unavailable",
    }
    first = await support.ticket_service.create_from_event(event)
    second = await support.ticket_service.create_from_event(event)
    assert first.ticket_id == second.ticket_id
    assert len(support.repository.outbox) == 1


@pytest.mark.asyncio
async def test_resolution_before_occurrence_creates_cancelled_tombstone() -> None:
    """验证解析之前创建对应的测试场景。"""
    container = build_memory_container()
    support = configure_memory_support(container)
    resolution = {
        "tenant_id": "tenant-1",
        "source": "expense-invoice-gate",
        "alert_id": "alert-late",
        "alert_type": "stale_invoice_gate_block",
        "resolution": "condition_cleared",
        "resolved_at": "2026-10-21T00:00:00+00:00",
        "text": "invoice gate alert resolved",
    }

    ticket = await support.ticket_service.resolve_invoice_gate_alert(resolution)
    occurrence = await support.ticket_service.create_from_event(
        {
            "tenant_id": "tenant-1",
            "source": "expense-invoice-gate",
            "message_id": "alert-late",
            "text": "invoice gate alert occurred",
        }
    )

    assert ticket.status == TicketStatus.CANCELLED
    assert ticket.metadata["resolution"]["reason"] == "condition_cleared"
    assert occurrence.ticket_id == ticket.ticket_id
    assert occurrence.status == TicketStatus.CANCELLED


def test_webhook_returns_high_risk_ticket() -> None:
    """验证Webhook返回高风险工单对应的测试场景。"""
    client = TestClient(create_platform_app(build_memory_container()))
    response = client.post(
        "/v1/events/im",
        json={
            "tenant_id": "tenant-1",
            "source": "feishu",
            "message_id": "msg-3",
            "text": "I want a refund and I have a complaint",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "waiting_approval"
    assert body["risk_level"] == "high"


def test_approval_api_moves_ticket_to_ready_to_publish() -> None:
    """验证审批API移动工单到到发布对应的测试场景。"""
    client = TestClient(create_platform_app(build_memory_container()))
    created = client.post(
        "/v1/events/im",
        json={
            "tenant_id": "tenant-1",
            "source": "feishu",
            "message_id": "msg-4",
            "text": "I want a refund",
        },
    ).json()
    response = client.post(
        f"/v1/tickets/{created['ticket_id']}/approve",
        json={"tenant_id": "tenant-1", "decided_by": "supervisor-1"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ready_to_publish"


def test_reply_api_publishes_approved_ticket() -> None:
    """验证回复API发布已批准工单对应的测试场景。"""
    container = build_memory_container()
    support = configure_memory_support(container)
    outcome = asyncio.run(
        support.processing_service.process_event(
            {
                "tenant_id": "tenant-1",
                "source": "feishu",
                "message_id": "reply-msg-1",
                "text": "I want a refund",
                "reply_target": "chat-1",
            }
        )
    )
    asyncio.run(
        support.ticket_service.apply_approval(
            tenant_id="tenant-1",
            ticket_id=outcome.ticket_id,
            decision="approve",
            decided_by="supervisor-1",
        )
    )
    client = TestClient(create_app_with_support(container, support))
    response = client.post(
        f"/v1/tickets/{outcome.ticket_id}/reply",
        json={
            "tenant_id": "tenant-1",
            "text": "Your refund request has been received.",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "published"
    assert support.reply_connector.messages[0]["target"] == "chat-1"


def test_reply_api_requires_non_empty_text() -> None:
    """验证回复API要求非空文本对应的测试场景。"""
    client = TestClient(create_platform_app(build_memory_container()))

    response = client.post(
        "/v1/tickets/ticket-1/reply",
        json={"tenant_id": "tenant-1", "text": "   "},
    )

    assert response.status_code == 422
