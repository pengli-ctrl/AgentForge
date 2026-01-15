"""AgentForge 平台基础设施层：memory_knowledge_repository。

本模块提供 memory_knowledge_repository 的内存实现，用于单元测试、本地开发和离线验证。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：MemoryKnowledgeRepository。
"""

from __future__ import annotations

from agentforge.platform.application.knowledge_embedder import (
    EMBEDDING_MODEL,
    EMBEDDING_VERSION,
    Embedder,
    HashEmbedder,
    cosine_similarity,
)
from agentforge.platform.domain.knowledge import KnowledgeChunk, KnowledgeDocument, RetrievedChunk
from agentforge.platform.infrastructure.hybrid_scores import fuse_scores, merge_retrieved_chunks


class MemoryKnowledgeRepository:
    """MemoryKnowledgeRepository。

    MemoryKnowledgeRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 save_document()。
    - 方法 backfill_embeddings()。
    - 方法 search()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, embedder: Embedder | None = None) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            embedder: Embedder | None，调用方传入的 embedder 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.documents: dict[str, KnowledgeDocument] = {}
        self.chunks: list[KnowledgeChunk] = []
        self._embedder = embedder or HashEmbedder()

    def _embed(self, chunk: KnowledgeChunk) -> None:
        """执行 _embed 对应的逻辑，并返回处理结果。

        Args:
            chunk: KnowledgeChunk，调用方传入的 chunk 参数。

        Returns:
            None，函数执行后的结果。
        """
        if chunk.embedding is None:
            chunk.embedding = self._embedder.embed(
                f"{self.documents[chunk.document_id].title} {chunk.content}"
            )
            chunk.embedding_model = EMBEDDING_MODEL
            chunk.embedding_version = EMBEDDING_VERSION

    async def save_document(
        self,
        document: KnowledgeDocument,
        chunks: list[KnowledgeChunk],
    ) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            document: KnowledgeDocument，调用方传入的 document 参数。
            chunks: list[KnowledgeChunk]，调用方传入的 chunks 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.documents[document.document_id] = document
        for chunk in chunks:
            self._embed(chunk)
        self.chunks.extend(chunks)

    async def backfill_embeddings(self, tenant_id: str | None = None) -> int:
        """回填缺失数据，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。

        Returns:
            int，函数执行后的结果。
        """
        count = 0
        for chunk in self.chunks:
            if tenant_id and chunk.tenant_id != tenant_id:
                continue
            if chunk.embedding is None:
                self._embed(chunk)
                count += 1
        return count

    async def search(
        self,
        tenant_id: str,
        query: str,
        limit: int = 5,
        mode: str = "hybrid",
        fts_weight: float = 0.5,
        vector_weight: float = 0.5,
    ) -> list[RetrievedChunk]:
        """执行 search 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            query: str，调用方传入的 query 参数。
            limit: int，调用方传入的 limit 参数。
            mode: str，调用方传入的 mode 参数。
            fts_weight: float，调用方传入的 fts_weight 参数。
            vector_weight: float，调用方传入的 vector_weight 参数。

        Returns:
            list[RetrievedChunk]，函数执行后的结果。
        """
        terms = [term.lower() for term in query.split() if len(term) > 2]
        query_vector = self._embedder.embed(query)

        keyword_scores: dict[str, float] = {}
        vector_scores: dict[str, float] = {}
        chunks_by_id: dict[str, RetrievedChunk] = {}

        for chunk in self.chunks:
            if chunk.tenant_id != tenant_id:
                continue
            document = self.documents[chunk.document_id]
            haystack = f"{document.title} {chunk.content}".lower()
            keyword_score = 0.0
            if terms:
                keyword_score = sum(1.0 for term in terms if term in haystack) / len(terms)
            vector_score = (
                cosine_similarity(query_vector, chunk.embedding)
                if chunk.embedding is not None
                else 0.0
            )
            if mode == "keyword" and keyword_score <= 0.0:
                continue
            if mode == "vector" and vector_score <= 0.0:
                continue
            if mode == "hybrid" and keyword_score <= 0.0 and vector_score <= 0.0:
                continue
            keyword_scores[chunk.chunk_id] = keyword_score
            vector_scores[chunk.chunk_id] = vector_score
            chunks_by_id[chunk.chunk_id] = RetrievedChunk(
                chunk_id=chunk.chunk_id,
                document_id=document.document_id,
                tenant_id=tenant_id,
                title=document.title,
                content=chunk.content,
                score=0.0,
                source_uri=document.source_uri,
                fts_score=keyword_score,
                vector_score=vector_score,
            )

        fused = fuse_scores(keyword_scores, vector_scores, fts_weight, vector_weight)
        remaining = {key: value for key, value in fused.items() if key in chunks_by_id}
        results = merge_retrieved_chunks(chunks_by_id, remaining, mode)
        return results[:limit]
