import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.domain.ticket import RiskLevel
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.sqlalchemy_evaluation_repository import (
    SQLAlchemyEvaluationRepository,
)
from agentforge.platform.runtime import build_memory_container


def create_ticket(container, message_id: str):
    async def setup():
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


def test_review_actions_create_evaluation_samples_and_summary() -> None:
    container = build_memory_container()

    async def ingest():
        await container.knowledge_service.ingest_document(
            tenant_id="tenant-1",
            title="Product usage",
            content="How to use this product: open the dashboard and follow the setup guide.",
        )

    asyncio.run(ingest())
    accepted = create_ticket(container, "eval-msg-1")
    edited = create_ticket(container, "eval-msg-2")
    rejected = create_ticket(container, "eval-msg-3")
    client = TestClient(create_platform_app(container))

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
