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
    def __init__(
        self,
        repository: KnowledgeRepository,
        chunker: SimpleTextChunker | None = None,
        embedder: Embedder | None = None,
        reranker: Reranker | None = None,
    ) -> None:
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
        """为缺失 embedding 的旧数据回填向量，返回回填条数。"""
        return await self._repository.backfill_embeddings(tenant_id)
