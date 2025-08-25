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
    def __init__(self, embedder: Embedder | None = None) -> None:
        self.documents: dict[str, KnowledgeDocument] = {}
        self.chunks: list[KnowledgeChunk] = []
        self._embedder = embedder or HashEmbedder()

    def _embed(self, chunk: KnowledgeChunk) -> None:
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
        self.documents[document.document_id] = document
        for chunk in chunks:
            self._embed(chunk)
        self.chunks.extend(chunks)

    async def backfill_embeddings(self, tenant_id: str | None = None) -> int:
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
