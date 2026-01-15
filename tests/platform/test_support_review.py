"""AgentForge 平台测试层：test_support_review。

本测试模块验证 test_support_review 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：create_low_risk_ticket、test_accept_reviewed_draft_and_publish_it、test_edit_reviewed_draft_before_publish、test_reject_reviewed_draft_and_keep_tenant_isolation。
"""

import asyncio

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.runtime import build_memory_container


def create_low_risk_ticket(container, message_id: str):
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        container: Any，调用方传入的 container 参数。
        message_id: str，调用方传入的 message_id 参数。

    Returns:
        None，函数执行后的结果。
    """

    async def setup():
        """执行 setup 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
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
    """验证 accept_reviewed_draft_and_publish_it 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
    """验证 edit_reviewed_draft_before_publish 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
    """验证 reject_reviewed_draft_and_keep_tenant_isolation 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
