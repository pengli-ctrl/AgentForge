"""评估测试模块。

本测试模块验证 test_evaluation_feedback 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：create_ticket、test_review_actions_create_evaluation_samples_and_summary、test_sqlalchemy_eva
    luation_repository_summary。
"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.sqlalchemy_evaluation_repository import (
    SQLAlchemyEvaluationRepository,
)
from agentforge.platform.modules.support.domain.ticket import RiskLevel
from agentforge.platform.runtime import build_memory_container
from tests.platform.support_fixtures import configure_memory_support, create_app_with_support


def create_ticket(support, message_id: str):
    """创建工单。

    Args:
        support: 客服。
        message_id: 消息 ID。

    Returns:
        处理结果。
    """

    async def setup():
        """装配测试环境。

        Returns:
            处理结果。
        """
        return await support.processing_service.process_event(
            {
                "tenant_id": "tenant-1",
                "source": "feishu",
                "message_id": message_id,
                "text": "How do I use this product?",
                "reply_target": "chat-1",
            }
        )

    return asyncio.run(setup())


def test_review_actions_create_evaluation_samples_and_summary() -> None:
    """验证审核操作创建评估样本及摘要对应的测试场景。"""
    container = build_memory_container()
    support = configure_memory_support(container)

    async def ingest():
        """写入数据。"""
        await container.knowledge_service.ingest_document(
            tenant_id="tenant-1",
            title="Product usage",
            content="How to use this product: open the dashboard and follow the setup guide.",
        )

    asyncio.run(ingest())
    accepted = create_ticket(support, "eval-msg-1")
    edited = create_ticket(support, "eval-msg-2")
    rejected = create_ticket(support, "eval-msg-3")
    client = TestClient(create_app_with_support(container, support))

    client.post(
        f"/v1/tickets/{accepted.ticket_id}/review",
        json={"tenant_id": "tenant-1", "reviewer_id": "agent-1", "action": "accept"},
    )
    client.post(
        f"/v1/tickets/{edited.ticket_id}/review",
        json={
            "tenant_id": "tenant-1",
            "reviewer_id": "agent-1",
            "action": "edit",
            "edited_text": "Open the dashboard and finish setup.",
        },
    )
    client.post(
        f"/v1/tickets/{rejected.ticket_id}/review",
        json={
            "tenant_id": "tenant-1",
            "reviewer_id": "agent-2",
            "action": "reject",
            "reason": "Missing plan-specific details.",
        },
    )

    summary = client.get("/v1/evaluations/summary", params={"tenant_id": "tenant-1"}).json()
    assert summary["sample_count"] == 3
    assert summary["action_counts"] == {"accept": 1, "edit": 1, "reject": 1}
    assert summary["acceptance_rate"] == pytest.approx(1 / 3)
    assert summary["draft_useful_rate"] == pytest.approx(2 / 3)

    samples = client.get(
        "/v1/evaluations/samples",
        params={"tenant_id": "tenant-1", "action": "edit"},
    ).json()["samples"]
    assert len(samples) == 1
    assert samples[0]["source_ticket_id"] == edited.ticket_id
    assert samples[0]["final_text"] == "Open the dashboard and finish setup."
    assert samples[0]["model_name"]


@pytest.mark.asyncio
async def test_sqlalchemy_evaluation_repository_summary() -> None:
    """验证SQLAlchemy评估仓储摘要对应的测试场景。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = SQLAlchemyEvaluationRepository(session_factory)
    from agentforge.platform.domain.evaluation import EvaluationSample

    sample = EvaluationSample(
        sample_id="sample-1",
        tenant_id="tenant-1",
        source_ticket_id="ticket-1",
        query="question",
        draft_text="draft",
        final_text="draft",
        action="accept",
        reviewer_id="agent-1",
        risk_level=RiskLevel.LOW,
        trace_id="trace-1",
    )
    await repository.save(sample)
    summary = await repository.summary("tenant-1")

    assert summary["sample_count"] == 1
    assert summary["acceptance_rate"] == 1.0
    await engine.dispose()
