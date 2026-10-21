"""审计及成本API测试模块。

本测试模块验证 test_audit_and_cost_api 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：create_completed_ticket、test_audit_and_cost_summary_cover_completed_ticket、test_sqlalchemy_
    audit_repository_round_trip。
"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.sqlalchemy_audit_repository import SQLAlchemyAuditRepository
from agentforge.platform.runtime import build_memory_container
from tests.platform.support_fixtures import configure_memory_support, create_app_with_support


def create_completed_ticket(container, support):
    """创建已完成工单。

    Args:
        container: 服务容器。
        support: 客服。

    Returns:
        处理结果。
    """

    async def setup():
        """装配测试环境。

        Returns:
            处理结果。
        """
        await container.knowledge_service.ingest_document(
            tenant_id="tenant-1",
            title="Product usage",
            content="How to use this product: open the dashboard and follow the setup guide.",
        )
        ticket = await support.processing_service.process_event(
            {
                "tenant_id": "tenant-1",
                "source": "feishu",
                "message_id": "audit-msg-1",
                "text": "How do I use this product?",
                "reply_target": "chat-1",
            }
        )
        await support.ticket_service.review_draft(
            tenant_id="tenant-1",
            ticket_id=ticket.ticket_id,
            action="accept",
            reviewer_id="agent-1",
        )
        return await support.ticket_service.publish_reply("tenant-1", ticket.ticket_id)

    return asyncio.run(setup())


def test_audit_and_cost_summary_cover_completed_ticket() -> None:
    """验证审计及成本摘要已完成工单对应的测试场景。"""
    container = build_memory_container()
    support = configure_memory_support(container)
    ticket = create_completed_ticket(container, support)
    client = TestClient(create_app_with_support(container, support))

    audit_response = client.get(
        "/v1/audit",
        params={"tenant_id": "tenant-1", "resource_id": ticket.ticket_id},
    )
    assert audit_response.status_code == 200
    events = audit_response.json()["events"]
    assert {event["action"] for event in events} == {
        "ticket.created",
        "ticket.drafted",
        "ticket.review.accepted",
        "reply.published",
    }
    assert all(event["resource_id"] == ticket.ticket_id for event in events)
    assert all(event["trace_id"] for event in events)

    cost_response = client.get("/v1/costs/summary", params={"tenant_id": "tenant-1"})
    assert cost_response.status_code == 200
    summary = cost_response.json()
    assert summary["request_count"] == 1
    assert summary["by_model"][0]["model_name"]
    assert summary["input_tokens"] > 0


@pytest.mark.asyncio
async def test_sqlalchemy_audit_repository_round_trip() -> None:
    """验证SQLAlchemy审计仓储轮次往返对应的测试场景。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = SQLAlchemyAuditRepository(session_factory)
    event = AuditEvent(
        event_id="audit-1",
        tenant_id="tenant-1",
        action="ticket.created",
        resource_type="ticket",
        resource_id="ticket-1",
        actor_id="agent-1",
        trace_id="trace-1",
        payload={"source": "feishu"},
    )
    await repository.save(event)

    events = await repository.list_events("tenant-1", resource_id="ticket-1")

    assert len(events) == 1
    assert events[0].actor_id == "agent-1"
    assert events[0].trace_id == "trace-1"
    await engine.dispose()
