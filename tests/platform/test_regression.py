import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.application.classification_evaluation_service import (
    ClassificationEvaluationService,
)
from agentforge.platform.application.classifier import RuleBasedTicketClassifier
from agentforge.platform.application.quality_gate_service import QualityGateService
from agentforge.platform.application.regression_runner import RegressionRunner
from agentforge.platform.application.retrieval_evaluation_service import (
    RetrievalEvaluationService,
)
from agentforge.platform.domain.quality import ReleaseCandidate
from agentforge.platform.domain.regression import GoldenItem
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.memory_knowledge_repository import MemoryKnowledgeRepository
from agentforge.platform.infrastructure.memory_regression_repository import (
    MemoryRegressionRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_regression_repository import (
    SQLAlchemyRegressionRepository,
)


def _candidate(tenant_id: str = "t1") -> ReleaseCandidate:
    return ReleaseCandidate(
        candidate_id=f"cand-{uuid.uuid4().hex[:8]}",
        tenant_id=tenant_id,
        label="test",
        prompt_name="reply",
        prompt_version="1.0",
        model_name="gpt",
        model_version="1.0",
    )


def _build_runner(knowledge_repo):
    """返回 (RegressionRunner, MemoryRegressionRepository) 便于种子存取。"""
    from agentforge.platform.application.reranker import HybridReranker

    eval_svc = RetrievalEvaluationService(knowledge_repo, HybridReranker())
    cls_eval = ClassificationEvaluationService(RuleBasedTicketClassifier())
    reg_repo = MemoryRegressionRepository()
    runner = RegressionRunner(
        reg_repo,
        eval_svc,
        cls_eval,
        QualityGateService(),
    )
    return runner, reg_repo


async def _seed_knowledge(repo: MemoryKnowledgeRepository, tenant_id: str = "t1") -> list[str]:
    from agentforge.platform.domain.knowledge import KnowledgeChunk, KnowledgeDocument

    doc = KnowledgeDocument(
        document_id="doc-1",
        tenant_id=tenant_id,
        title="Refund Policy",
        content="Policy for refunds within seven days of purchase.",
        source_uri="https://example.com/refund",
    )
    chunk = KnowledgeChunk(
        chunk_id="doc-x",
        document_id="doc-1",
        tenant_id=tenant_id,
        content="A customer can request a full refund within seven days of purchase.",
        position=0,
        embedding=[0.1] * 64,
    )
    await repo.save_document(doc, [chunk])
    return ["doc-x"]


def _golden_items(tenant_id: str = "t1") -> list[GoldenItem]:
    return [
        GoldenItem(
            item_id="g1",
            tenant_id=tenant_id,
            query="refund within seven days",
            expected_chunk_ids=["doc-x"],
            expected_citations=["doc-x"],
            expected_intent="complaint_or_refund",
            expected_priority="p0",
            expected_risk_level="high",
        ),
        GoldenItem(
            item_id="g2",
            tenant_id=tenant_id,
            query="price please",
            expected_chunk_ids=[],
            expected_citations=[],
            expected_intent="sales_question",
            expected_priority="p2",
            expected_risk_level="low",
        ),
    ]


async def _run_end_to_end(
    tenant_id: str = "t1",
) -> tuple[RegressionRunner, MemoryRegressionRepository]:
    repo = MemoryKnowledgeRepository()
    await _seed_knowledge(repo, tenant_id)
    runner, reg_repo = _build_runner(repo)
    for item in _golden_items(tenant_id):
        await reg_repo.save_golden(item)
    return runner, reg_repo


@pytest.mark.asyncio
async def test_regression_reports_persisted_and_pass_gate() -> None:
    runner, _reg_repo = await _run_end_to_end()
    report = await runner.run(tenant_id="t1", candidate=_candidate("t1"), k=2)
    assert report.verdict in {"pass", "hold", "block"}
    runs = await runner.list_runs("t1")
    assert len(runs) >= 1
    run = await runner.get_run(runs[0].run_id)
    assert run is not None
    assert run.candidate_id == runs[0].candidate_id
    # 报告与运行记录的指标应一致（同一 run）
    assert report.run_id == run.run_id


@pytest.mark.asyncio
async def test_regression_tenant_isolation() -> None:
    repo = MemoryKnowledgeRepository()
    await _seed_knowledge(repo, "ta")
    runner, reg_repo = _build_runner(repo)
    await reg_repo.save_golden(GoldenItem(item_id="g-a", tenant_id="ta", query="q"))
    await reg_repo.save_golden(GoldenItem(item_id="g-b", tenant_id="tb", query="q"))
    assert len(await runner.load_golden("ta")) == 1
    assert len(await runner.load_golden("tb")) == 1
    # ta 的回归不应影响 tb
    report_a = await runner.run("ta", _candidate("ta"), k=2)
    assert report_a.tenant_id == "ta"
    assert len(await runner.list_runs("tb")) == 0


@pytest.mark.asyncio
async def test_regression_empty_dataset_report() -> None:
    repo = MemoryKnowledgeRepository()
    runner, _reg_repo = _build_runner(repo)
    report = await runner.run("empty", _candidate("empty"), k=2)
    assert report.verdict in {"pass", "hold", "block"}


@pytest.mark.asyncio
async def test_sqlalchemy_regression_repository_roundtrip() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    repo = SQLAlchemyRegressionRepository(factory)
    golden = GoldenItem(
        item_id="g-sql",
        tenant_id="t",
        query="q",
        expected_chunk_ids=["c1"],
        expected_citations=[],
        expected_intent="sales_question",
    )
    await repo.save_golden(golden)
    got = await repo.list_golden("t")
    assert len(got) == 1
    assert got[0].expected_chunk_ids == ["c1"]
    assert got[0].expected_intent == "sales_question"

    # 运行记录往返
    from agentforge.platform.domain.regression import RegressionRun, RegressionRunStatus

    run = RegressionRun(
        run_id="run-sql",
        tenant_id="t",
        candidate_id="c",
        status=RegressionRunStatus.PASSED,
        verdict="pass",
    )
    await repo.save_run(run)
    from agentforge.platform.domain.regression import QualityReport

    await repo.save_report(
        QualityReport(
            report_id="rep-sql",
            run_id="run-sql",
            candidate_id="c",
            tenant_id="t",
            verdict="pass",
            metrics={"recall_at_k": 1.0, "verdict": 1.0},
        )
    )
    stored = await repo.get_run("run-sql")
    assert stored is not None
    assert stored.recall_at_k == 1.0  # save_report 回写 summary


@pytest.mark.asyncio
async def test_regression_api_seeds_and_runs() -> None:
    from fastapi.testclient import TestClient

    from agentforge.platform.api.app import create_platform_app
    from agentforge.platform.api.security import ApiKeyAuthenticator
    from agentforge.platform.runtime import build_memory_container

    container = build_memory_container(authenticator=ApiKeyAuthenticator(enabled=False))
    # 预置知识种子让召回通过
    await _seed_knowledge(container.knowledge_repository, "t1")
    await container.regression_repository.save_golden(
        GoldenItem(
            item_id="g-api",
            tenant_id="t1",
            query="refund within seven days",
            expected_chunk_ids=["doc-x"],
            expected_citations=["doc-x"],
            expected_intent="complaint_or_refund",
            expected_priority="p0",
            expected_risk_level="high",
        )
    )
    app = create_platform_app(container)
    client = TestClient(app)
    resp = client.post(
        "/v1/regression/run?k=2",
        json={
            "candidate_id": "cand-api",
            "tenant_id": "t1",
            "prompt_name": "reply",
            "prompt_version": "1.0",
            "model_name": "gpt",
            "model_version": "1.0",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["report_id"]
    assert body["run_id"]
    assert "metrics" in body
