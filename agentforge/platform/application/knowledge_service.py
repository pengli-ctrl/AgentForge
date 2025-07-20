from __future__ import annotations

from uuid import uuid4

from agentforge.platform.application.ports import KnowledgeRepository
from agentforge.platform.application.text_chunker import SimpleTextChunker
from agentforge.platform.domain.knowledge import KnowledgeChunk, KnowledgeDocument, RetrievedChunk


class KnowledgeService:
    def __init__(
        self, repository: KnowledgeRepository, chunker: SimpleTextChunker | None = None
    ) -> None:
        self._repository = repository
        self._chunker = chunker or SimpleTextChunker()

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
            )
            for position, text in enumerate(self._chunker.split(content))
        ]
        await self._repository.save_document(document, chunks)
        return document

    async def search(self, tenant_id: str, query: str, limit: int = 5) -> list[RetrievedChunk]:
        return await self._repository.search(tenant_id, query, limit)
