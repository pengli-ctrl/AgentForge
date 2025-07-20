from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.knowledge import KnowledgeChunk, KnowledgeDocument, RetrievedChunk
from agentforge.platform.infrastructure.db.models import (
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
)


class SQLAlchemyKnowledgeRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_document(
        self,
        document: KnowledgeDocument,
        chunks: list[KnowledgeChunk],
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                session.add(
                    KnowledgeDocumentRecord(
                        document_id=document.document_id,
                        tenant_id=document.tenant_id,
                        title=document.title,
                        content=document.content,
                        source_uri=document.source_uri,
                        version=document.version,
                        payload=document.metadata,
                    )
                )
                for chunk in chunks:
                    session.add(
                        KnowledgeChunkRecord(
                            chunk_id=chunk.chunk_id,
                            document_id=chunk.document_id,
                            tenant_id=chunk.tenant_id,
                            content=chunk.content,
                            position=chunk.position,
                            payload=chunk.metadata,
                        )
                    )

    async def search(
        self,
        tenant_id: str,
        query: str,
        limit: int = 5,
    ) -> list[RetrievedChunk]:
        terms = [term for term in query.split() if len(term) > 2]
        if not terms:
            return []
        predicates = []
        for term in terms:
            pattern = f"%{term}%"
            predicates.extend(
                [
                    KnowledgeChunkRecord.content.ilike(pattern),
                    KnowledgeDocumentRecord.title.ilike(pattern),
                ]
            )
        async with self._session_factory() as session:
            statement = (
                select(KnowledgeChunkRecord, KnowledgeDocumentRecord)
                .join(
                    KnowledgeDocumentRecord,
                    KnowledgeChunkRecord.document_id == KnowledgeDocumentRecord.document_id,
                )
                .where(
                    KnowledgeChunkRecord.tenant_id == tenant_id,
                    or_(*predicates),
                )
                .limit(limit)
            )
            rows = (await session.execute(statement)).all()
            return [
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    document_id=document.document_id,
                    tenant_id=chunk.tenant_id,
                    title=document.title,
                    content=chunk.content,
                    score=1.0,
                    source_uri=document.source_uri,
                )
                for chunk, document in rows
            ]
