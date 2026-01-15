"""AgentForge 平台测试层：test_hybrid_retrieval。

本测试模块验证 test_hybrid_retrieval 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：make_document、test_hybrid_recall_returns_keyword_hits、test_tenant_isolation、test_search_empty_repository_and_no_match、test_mode_keyword_versus_vector、test_backfill_embeddings。
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.domain.knowledge import KnowledgeChunk, KnowledgeDocument
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.memory_knowledge_repository import MemoryKnowledgeRepository
from agentforge.platform.infrastructure.sqlalchemy_knowledge_repository import (
    SQLAlchemyKnowledgeRepository,
)


def make_document(
    tenant_id: str, title: str, content: str
) -> tuple[KnowledgeDocument, list[KnowledgeChunk]]:
    """执行 make_document 对应的逻辑，并返回处理结果。

    Args:
        tenant_id: str，调用方传入的 tenant_id 参数。
        title: str，调用方传入的 title 参数。
        content: str，调用方传入的 content 参数。

    Returns:
        tuple[KnowledgeDocument, list[KnowledgeChunk]]，函数执行后的结果。
    """
    document = KnowledgeDocument(
        document_id=f"doc-{tenant_id}-{title}",
        tenant_id=tenant_id,
        title=title,
        content=content,
        source_uri=f"uri-{tenant_id}-{title}",
    )
    chunks = [
        KnowledgeChunk(
            chunk_id=f"chunk-{tenant_id}-{title}",
            document_id=document.document_id,
            tenant_id=tenant_id,
            content=content,
            position=0,
            metadata={"source_uri": document.source_uri},
        )
    ]
    return document, chunks


# 常量：DOCS。
DOCS = [
    (
        "tenant-1",
        "Refund policy",
        "Customers can request a refund within seven days for product issues.",
    ),
    (
        "tenant-1",
        "Shipping guide",
        "Standard shipping takes three to five business days nationwide.",
    ),
    ("tenant-2", "Refund policy", "Tenant two offers a thirty day money back refund guarantee."),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("repository_factory", ["memory", "sqlalchemy"])
async def test_hybrid_recall_returns_keyword_hits(repository_factory: str) -> None:
    """验证 hybrid_recall_returns_keyword_hits 对应的业务行为、边界条件和回归场景。

    Args:
        repository_factory: str，调用方传入的 repository_factory 参数。

    Returns:
        None，函数执行后的结果。
    """
    repository = await _build(repository_factory)
    for tenant_id, title, content in DOCS:
        document, chunks = make_document(tenant_id, title, content)
        await repository.save_document(document, chunks)

    results = await repository.search("tenant-1", "refund", limit=5, mode="hybrid")
    assert len(results) >= 1
    assert any("Refund" in result.title for result in results)


@pytest.mark.asyncio
@pytest.mark.parametrize("repository_factory", ["memory", "sqlalchemy"])
async def test_tenant_isolation(repository_factory: str) -> None:
    """验证 tenant_isolation 对应的业务行为、边界条件和回归场景。

    Args:
        repository_factory: str，调用方传入的 repository_factory 参数。

    Returns:
        None，函数执行后的结果。
    """
    repository = await _build(repository_factory)
    for tenant_id, title, content in DOCS:
        document, chunks = make_document(tenant_id, title, content)
        await repository.save_document(document, chunks)

    results = await repository.search("tenant-1", "money back refund", limit=10, mode="hybrid")
    # tenant-1 检索不到任何 tenant-2 的文档
    assert all(result.tenant_id == "tenant-1" for result in results)
    # tenant-1 自己的 refund 文档必须被召回到
    assert any(result.chunk_id == "chunk-tenant-1-Refund policy" for result in results)


@pytest.mark.asyncio
@pytest.mark.parametrize("repository_factory", ["memory", "sqlalchemy"])
async def test_search_empty_repository_and_no_match(repository_factory: str) -> None:
    """验证 search_empty_repository_and_no_match 对应的业务行为、边界条件和回归场景。

    Args:
        repository_factory: str，调用方传入的 repository_factory 参数。

    Returns:
        None，函数执行后的结果。
    """
    repository = await _build(repository_factory)
    assert await repository.search("tenant-1", "anything", mode="hybrid") == []
    # 空查询
    assert await repository.search("tenant-1", "   ", mode="hybrid") == []
    # 不相关关键词
    assert await repository.search("tenant-missing", "refund", mode="hybrid") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("repository_factory", ["memory", "sqlalchemy"])
async def test_mode_keyword_versus_vector(repository_factory: str) -> None:
    """验证 mode_keyword_versus_vector 对应的业务行为、边界条件和回归场景。

    Args:
        repository_factory: str，调用方传入的 repository_factory 参数。

    Returns:
        None，函数执行后的结果。
    """
    repository = await _build(repository_factory)
    for tenant_id, title, content in DOCS:
        document, chunks = make_document(tenant_id, title, content)
        await repository.save_document(document, chunks)

    keyword = await repository.search("tenant-1", "refund", limit=5, mode="keyword")
    vector = await repository.search("tenant-1", "refund", limit=5, mode="vector")
    hybrid = await repository.search("tenant-1", "refund", limit=5, mode="hybrid")
    assert all(result.mode == "keyword" for result in keyword)
    assert all(result.mode == "vector" for result in vector)
    assert all(result.mode == "hybrid" for result in hybrid)
    # keyword/vector/hybrid 任一模式都必须能召回到关键词命中的文档
    assert any("Refund" in r.title for r in keyword)
    assert any("Refund" in r.title for r in vector)
    assert any("Refund" in r.title for r in hybrid)


@pytest.mark.asyncio
@pytest.mark.parametrize("repository_factory", ["memory", "sqlalchemy"])
async def test_backfill_embeddings(repository_factory: str) -> None:
    """验证 backfill_embeddings 对应的业务行为、边界条件和回归场景。

    Args:
        repository_factory: str，调用方传入的 repository_factory 参数。

    Returns:
        None，函数执行后的结果。
    """
    repository = await _build(repository_factory)
    for tenant_id, title, content in DOCS:
        document, chunks = make_document(tenant_id, title, content)
        await repository.save_document(document, chunks)
    backfilled = await repository.backfill_embeddings("tenant-1")
    assert backfilled >= 0
    # 再次回填应幂等（不会重复增加）
    assert await repository.backfill_embeddings("tenant-1") == 0


async def _build(kind: str):
    """执行 _build 对应的逻辑，并返回处理结果。

    Args:
        kind: str，调用方传入的 kind 参数。

    Returns:
        None，函数执行后的结果。
    """
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
