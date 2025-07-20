import asyncio

import pytest
from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.domain.ticket import TicketStatus
from agentforge.platform.runtime import build_memory_container


@pytest.mark.asyncio
async def test_low_risk_event_creates_ticket_waiting_review() -> None:
    container = build_memory_container()
    event = {
        "tenant_id": "tenant-1",
        "source": "feishu",
        "message_id": "msg-1",
        "text": "How do I use this product?",
    }
    ticket = await container.ticket_service.create_from_event(event)
    assert ticket.status == TicketStatus.WAITING_REVIEW
    assert ticket.assigned_team == "support"
    assert len(container.repository.outbox) == 1


@pytest.mark.asyncio
async def test_duplicate_event_returns_existing_ticket() -> None:
    container = build_memory_container()
    event = {
        "tenant_id": "tenant-1",
        "source": "feishu",
        "message_id": "msg-2",
        "text": "The product is unavailable",
    }
    first = await container.ticket_service.create_from_event(event)
    second = await container.ticket_service.create_from_event(event)
    assert first.ticket_id == second.ticket_id
    assert len(container.repository.outbox) == 1


def test_webhook_returns_high_risk_ticket() -> None:
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
    container = build_memory_container()
    outcome = asyncio.run(
        container.processing_service.process_event(
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
        container.ticket_service.apply_approval(
            tenant_id="tenant-1",
            ticket_id=outcome.ticket_id,
            decision="approve",
            decided_by="supervisor-1",
        )
    )
    client = TestClient(create_platform_app(container))
    response = client.post(
        f"/v1/tickets/{outcome.ticket_id}/reply",
        json={
            "tenant_id": "tenant-1",
            "text": "Your refund request has been received.",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "published"
    assert container.reply_connector.messages[0]["target"] == "chat-1"


def test_reply_api_requires_non_empty_text() -> None:
    client = TestClient(create_platform_app(build_memory_container()))

    response = client.post(
        "/v1/tickets/ticket-1/reply",
        json={"tenant_id": "tenant-1", "text": "   "},
    )

    assert response.status_code == 422
