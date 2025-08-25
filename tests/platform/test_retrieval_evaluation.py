import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.application.reranker import HybridReranker
from agentforge.platform.application.retrieval_evaluation_service import (
    RetrievalEvaluationService,
)
from agentforge.platform.application.retrieval_metrics import (
    citation_accuracy,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)
from agentforge.platform.domain.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    RetrievedChunk,
)
from agentforge.platform.domain.retrieval import GoldenQuery
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.memory_knowledge_repository import MemoryKnowledgeRepository
from agentforge.platform.infrastructure.sqlalchemy_knowledge_repository import (
    SQLAlchemyKnowledgeRepository,
)


@pytest.mark.parametrize(
    "relevant,retrieved,k,expected",
    [
        ({"a", "b", "c"}, ["a", "b", "x", "y"], 2, 2 / 3),
        ({"a", "b", "c"}, ["a", "b", "c"], 3, 1.0),
        ({"a", "b", "c"}, ["x", "y"], 5, 0.0),
        (set(), ["a"], 5, 0.0),  # 空相关集避免除零
    ],
)
def test_recall_at_k(relevant, retrieved, k, expected) -> None:
    assert recall_at_k(relevant, retrieved, k) == expected


def test_precision_at_k() -> None:
    relevant = {"a", "b"}
    assert precision_at_k(relevant, ["a", "c", "d"], k=3) == 1 / 3
    assert precision_at_k(relevant, ["a", "b"], k=2) == 1.0
    assert precision_at_k(relevant, []) == 0.0


def test_mean_reciprocal_rank() -> None:
    queries = [
        ({"a", "b"}, ["x", "a", "b"]),  # 首命中位置 2 -> 0.5
        ({"c"}, ["c", "d"]),  # 首命中位置 1 -> 1.0
        ({"z"}, ["x", "y"]),  # 无命中 -> 0.0
    ]
    assert mean_reciprocal_rank(queries) == pytest.approx((0.5 + 1.0 + 0.0) / 3)
    assert mean_reciprocal_rank([]) == 0.0


def test_citation_accuracy() -> None:
    relevant = {"a", "b", "c"}
    assert citation_accuracy(["a", "c"], relevant) == 1.0
    assert citation_accuracy(["a", "zz"], relevant) == 0.5
    assert citation_accuracy([], relevant) == 0.0


def _chunk(chunk_id: str, title: str, content: str, fts: float, vec: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc",
        tenant_id="t1",
        title=title,
        content=content,
        score=0.0,
        fts_score=fts,
        vector_score=vec,
    )


def test_hybrid_reranker_prefers_keyword_coverage() -> None:
    reranker = HybridReranker()
    candidates = [
        _chunk(
            "exact",
            "Refund policy",
            "Customers can request a refund within seven days.",
            0.9,
            0.1,
        ),
        _chunk(
            "irrelevant",
            "Shipping guide",
            "Standard shipping takes several business days.",
            0.2,
            0.8,
        ),
    ]
    # 查询 "refund" 时，"exact" 命中关键词应排到前面，即使向量分更低
    reranked = reranker.rerank("refund", candidates)
    assert reranked[0].chunk_id == "exact"


async def _build(kind: str):
    if kind == "memory":
        return MemoryKnowledgeRepository()
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return SQLAlchemyKnowledgeRepository(session_factory)


async def _seed(repository) -> None:
    docs = [
        (
            "t1",
            "doc-refund",
            "doc-refund",
            "Refund policy",
            "Customers can request a refund within seven days for product issues.",
        ),
        (
            "t1",
            "doc-shipping",
            "doc-shipping",
            "Shipping guide",
            "Standard shipping takes three to five business days nationwide.",
        ),
        ("t2", "doc-secret", "doc-secret", "Refund secrets", "Tenant two private refund manual."),
    ]
    for tenant_id, doc_id, chunk_id, title, content in docs:
        document = KnowledgeDocument(
            document_id=doc_id, tenant_id=tenant_id, title=title, content=content
        )
        chunk = KnowledgeChunk(
            chunk_id=chunk_id,
            document_id=doc_id,
            tenant_id=tenant_id,
            content=content,
            position=0,
        )
        await repository.save_document(document, [chunk])


async def _run_evaluation(kind: str) -> None:
    repository = await _build(kind)
    await _seed(repository)
    service = RetrievalEvaluationService(repository, HybridReranker())
    queries = [
        GoldenQuery(
            tenant_id="t1",
            query="refund within seven days",
            expected_chunk_ids=["doc-refund"],
            expected_citations=["doc-refund"],
        ),
        GoldenQuery(
            tenant_id="t1",
            query="shipping business days",
            expected_chunk_ids=["doc-shipping"],
            expected_citations=["doc-shipping"],
        ),
    ]
    report = await service.evaluate(queries, k=5, rerank=True)
    assert report.query_count == 2
    assert report.recall_at_k == 1.0
    assert report.mean_reciprocal_rank == 1.0
    assert report.citation_accuracy == 1.0
    assert 0.0 <= report.precision_at_k <= 1.0


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["memory", "sqlalchemy"])
async def test_retrieval_evaluation_scores(kind: str) -> None:
    await _run_evaluation(kind)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["memory", "sqlalchemy"])
async def test_evaluation_tenant_isolation(kind: str) -> None:
    repository = await _build(kind)
    await _seed(repository)
    service = RetrievalEvaluationService(repository, HybridReranker())
    queries = [
        GoldenQuery(
            tenant_id="t2",
            query="refund manual",
            expected_chunk_ids=["doc-secret"],
            expected_citations=["doc-secret"],
        ),
    ]
    report = await service.evaluate(queries, k=5, rerank=True)
    assert report.recall_at_k == 1.0
    assert all(evaluation.retrieved_chunks[0].tenant_id == "t2" for evaluation in report.per_query)
