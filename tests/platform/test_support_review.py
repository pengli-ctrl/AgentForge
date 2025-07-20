import asyncio

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.runtime import build_memory_container


def create_low_risk_ticket(container, message_id: str):
    async def setup():
        await container.knowledge_service.ingest_document(
            tenant_id="tenant-1",
            title="Product usage",
            content="How to use this product: open the dashboard and follow the setup guide.",
        )
        return await container.processing_service.process_event(
            {
                "tenant_id": "tenant-1",
                "source": "feishu",
                "message_id": message_id,
                "text": "How do I use this product?",
                "reply_target": "chat-1",
            }
        )

    return asyncio.run(setup())


def test_accept_reviewed_draft_and_publish_it() -> None:
    container = build_memory_container()
    ticket = create_low_risk_ticket(container, "review-msg-1")
    client = TestClient(create_platform_app(container))

    reviewed = client.post(
        f"/v1/tickets/{ticket.ticket_id}/review",
        json={
            "tenant_id": "tenant-1",
            "reviewer_id": "agent-1",
            "action": "accept",
        },
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "ready_to_publish"
    assert reviewed.json()["metadata"]["review"]["reviewer_id"] == "agent-1"

    published = client.post(
        f"/v1/tickets/{ticket.ticket_id}/reply",
        json={"tenant_id": "tenant-1"},
    )
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert (
        container.reply_connector.messages[0]["text"]
        == "Draft response generated from approved knowledge."
    )


def test_edit_reviewed_draft_before_publish() -> None:
    container = build_memory_container()
    ticket = create_low_risk_ticket(container, "review-msg-2")
    client = TestClient(create_platform_app(container))

    reviewed = client.post(
        f"/v1/tickets/{ticket.ticket_id}/review",
        json={
            "tenant_id": "tenant-1",
            "reviewer_id": "agent-1",
            "action": "edit",
            "edited_text": "Open the dashboard and complete the setup guide.",
        },
    )
    assert reviewed.status_code == 200
    assert (
        reviewed.json()["metadata"]["draft"]["reply_text"]
        == "Open the dashboard and complete the setup guide."
    )

    published = client.post(
        f"/v1/tickets/{ticket.ticket_id}/reply",
        json={"tenant_id": "tenant-1"},
    )
    assert published.status_code == 200
    assert (
        container.reply_connector.messages[0]["text"]
        == "Open the dashboard and complete the setup guide."
    )


def test_reject_reviewed_draft_and_keep_tenant_isolation() -> None:
    container = build_memory_container()
    ticket = create_low_risk_ticket(container, "review-msg-3")
    client = TestClient(create_platform_app(container))

    rejected = client.post(
        f"/v1/tickets/{ticket.ticket_id}/review",
        json={
            "tenant_id": "tenant-1",
            "reviewer_id": "agent-1",
            "action": "reject",
            "reason": "The answer does not match the customer plan.",
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "escalated"
    assert rejected.json()["metadata"]["review"]["reason"].startswith("The answer")

    wrong_tenant = client.get(
        f"/v1/tickets/{ticket.ticket_id}",
        params={"tenant_id": "tenant-2"},
    )
    assert wrong_tenant.status_code == 404

    blocked_reply = client.post(
        f"/v1/tickets/{ticket.ticket_id}/reply",
        json={"tenant_id": "tenant-1"},
    )
    assert blocked_reply.status_code == 409
