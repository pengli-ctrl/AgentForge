"""知识服务模块。"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4

from agentforge.platform.application.knowledge_embedder import (
    EMBEDDING_MODEL,
    EMBEDDING_VERSION,
    Embedder,
    HashEmbedder,
)
from agentforge.platform.application.ports import KnowledgeRepository
from agentforge.platform.application.reranker import Reranker
from agentforge.platform.application.text_chunker import SimpleTextChunker
from agentforge.platform.domain.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    RetrievedChunk,
    SearchMode,
)


class KnowledgeService:
    """知识应用服务，编排领域用例及其副作用。"""

    def __init__(
        self,
        repository: KnowledgeRepository,
        chunker: SimpleTextChunker | None = None,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        """初始化 KnowledgeService。

        Args:
            repository: 数据仓储实现。
            chunker: 分块器。
            embedder: 向量化器。
            reranker: 重排器。
        """
        self._repository = repository
        self._chunker = chunker or SimpleTextChunker()
        self._embedder = embedder or HashEmbedder()
        self._reranker = reranker

    async def ingest_document(
        self,
        tenant_id: str,
        title: str,
        content: str,
        source_uri: str = "",
        metadata: Mapping[str, object] | None = None,
    ) -> KnowledgeDocument:
        """写入文档。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            title: 输入参数。
            content: 写入内容。
            source_uri: 来源URI。
            metadata: 附加元数据。

        Returns:
            知识文档结果。
        """
        document = KnowledgeDocument(
            document_id=str(uuid4()),
            tenant_id=tenant_id,
            title=title,
            content=content,
            source_uri=source_uri,
            metadata=dict(metadata or {}),
        )
        chunks = [
            KnowledgeChunk(
                chunk_id=str(uuid4()),
                document_id=document.document_id,
                tenant_id=tenant_id,
                content=text,
                position=position,
                metadata={"source_uri": source_uri, **dict(metadata or {})},
                embedding=self._embedder.embed(f"{title} {text}"),
                embedding_model=EMBEDDING_MODEL,
                embedding_version=EMBEDDING_VERSION,
            )
            for position, text in enumerate(self._chunker.split(content))
        ]
        await self._repository.save_document(document, chunks)
        return document

    async def search(
        self,
        tenant_id: str,
        query: str,
        limit: int = 5,
        mode: SearchMode = "hybrid",
        fts_weight: float = 0.5,
        vector_weight: float = 0.5,
        rerank: bool = False,
    ) -> list[RetrievedChunk]:
        """搜索知识。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            query: 检索或筛选查询。
            limit: 返回记录的最大数量。
            mode: 运行模式。
            fts_weight: 输入参数。
            vector_weight: 输入参数。
            rerank: 重排。

        Returns:
            结果列表。
        """
        results = await self._repository.search(
            tenant_id,
            query,
            limit,
            mode=mode,
            fts_weight=fts_weight,
            vector_weight=vector_weight,
        )
        if rerank and self._reranker is not None:
            results = self._reranker.rerank(query, results)
        return results

    async def backfill_embeddings(self, tenant_id: str | None = None) -> int:
        """回填向量。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            整数结果。
        """
        return await self._repository.backfill_embeddings(tenant_id)
