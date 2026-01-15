"""AgentForge 平台应用服务层：knowledge_service。

本模块实现 knowledge_service 应用服务，编排多个领域对象和基础设施组件完成业务流程。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：KnowledgeService。
"""

from __future__ import annotations

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
    """KnowledgeService。

    KnowledgeService 编排业务流程，协调仓储、模型、策略和外部连接器完成用例。

    主要成员：
    - 方法 ingest_document()。
    - 方法 search()。
    - 方法 backfill_embeddings()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        repository: KnowledgeRepository,
        chunker: SimpleTextChunker | None = None,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            repository: KnowledgeRepository，调用方传入的 repository 参数。
            chunker: SimpleTextChunker | None，调用方传入的 chunker 参数。
            embedder: Embedder | None，调用方传入的 embedder 参数。
            reranker: Reranker | None，调用方传入的 reranker 参数。

        Returns:
            None，函数执行后的结果。
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
    ) -> KnowledgeDocument:
        """执行 ingest_document 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            title: str，调用方传入的 title 参数。
            content: str，调用方传入的 content 参数。
            source_uri: str，调用方传入的 source_uri 参数。

        Returns:
            KnowledgeDocument，函数执行后的结果。
        """
        document = KnowledgeDocument(
            document_id=str(uuid4()),
            tenant_id=tenant_id,
            title=title,
            content=content,
            source_uri=source_uri,
        )
        chunks = [
            KnowledgeChunk(
                chunk_id=str(uuid4()),
                document_id=document.document_id,
                tenant_id=tenant_id,
                content=text,
                position=position,
                metadata={"source_uri": source_uri},
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
        """执行 search 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            query: str，调用方传入的 query 参数。
            limit: int，调用方传入的 limit 参数。
            mode: SearchMode，调用方传入的 mode 参数。
            fts_weight: float，调用方传入的 fts_weight 参数。
            vector_weight: float，调用方传入的 vector_weight 参数。
            rerank: bool，调用方传入的 rerank 参数。

        Returns:
            list[RetrievedChunk]，函数执行后的结果。
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
        """回填缺失数据，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。

        Returns:
            int，函数执行后的结果。
        """
        return await self._repository.backfill_embeddings(tenant_id)
