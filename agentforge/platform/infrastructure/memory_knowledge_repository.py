from __future__ import annotations

from agentforge.platform.domain.knowledge import KnowledgeChunk, KnowledgeDocument, RetrievedChunk


class MemoryKnowledgeRepository:
    def __init__(self) -> None:
        self.documents: dict[str, KnowledgeDocument] = {}
        self.chunks: list[KnowledgeChunk] = []

    async def save_document(
        self,
        document: KnowledgeDocument,
        chunks: list[KnowledgeChunk],
    ) -> None:
        self.documents[document.document_id] = document
        self.chunks.extend(chunks)

    async def search(
        self,
        tenant_id: str,
        query: str,
        limit: int = 5,
    ) -> list[RetrievedChunk]:
        terms = [term.lower() for term in query.split() if len(term) > 2]
        results: list[RetrievedChunk] = []
        for chunk in self.chunks:
            if chunk.tenant_id != tenant_id:
                continue
            document = self.documents[chunk.document_id]
            haystack = f"{document.title} {chunk.content}".lower()
            if not any(term in haystack for term in terms):
                continue
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=document.document_id,
                    tenant_id=tenant_id,
                    title=document.title,
                    content=chunk.content,
                    score=1.0,
                    source_uri=document.source_uri,
                )
            )
            if len(results) >= limit:
                break
        return results
