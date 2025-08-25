from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.application.knowledge_embedder import (
    EMBEDDING_MODEL,
    EMBEDDING_VERSION,
    Embedder,
    HashEmbedder,
)
from agentforge.platform.domain.knowledge import KnowledgeChunk, KnowledgeDocument, RetrievedChunk
from agentforge.platform.infrastructure.db.models import (
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
)
from agentforge.platform.infrastructure.hybrid_scores import fuse_scores, merge_retrieved_chunks


class SQLAlchemyKnowledgeRepository:
    """PostgreSQL FTS + pgvector 混合检索仓储。

    方言分支：
    - postgresql：使用 `to_tsvector @@ plainto_tsquery` + `ts_rank`（FTS）与
      `embedding <=> query` 余弦距离（pgvector），关键词与向量相似度可合并排序。
    - 其他方言（例如 sqlite 测试库）：回退为 ILIKE 子串匹配 + Python 余弦，
      保持接口与单元测试等价，真实集成路径需在占位了 PostgreSQL 后验证。
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedder: Embedder | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._embedder = embedder or HashEmbedder()

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
                    embedding = chunk.embedding
                    if embedding is None:
                        embedding = self._embedder.embed(f"{document.title} {chunk.content}")
                    session.add(
                        KnowledgeChunkRecord(
                            chunk_id=chunk.chunk_id,
                            document_id=chunk.document_id,
                            tenant_id=chunk.tenant_id,
                            content=chunk.content,
                            position=chunk.position,
                            payload=chunk.metadata,
                            embedding=embedding,
                            embedding_model=chunk.embedding_model or EMBEDDING_MODEL,
                            embedding_version=chunk.embedding_version or EMBEDDING_VERSION,
                        )
                    )

    async def backfill_embeddings(self, tenant_id: str | None = None) -> int:
        backfilled = 0
        async with self._session_factory() as session:
            async with session.begin():
                statement = select(KnowledgeChunkRecord).where(
                    KnowledgeChunkRecord.embedding.is_(None)
                )
                if tenant_id:
                    statement = statement.where(KnowledgeChunkRecord.tenant_id == tenant_id)
                records = list((await session.execute(statement)).scalars().all())
                for record in records:
                    document = await session.get(KnowledgeDocumentRecord, record.document_id)
                    title = document.title if document else ""
                    record.embedding = self._embedder.embed(f"{title} {record.content}")
                    record.embedding_model = EMBEDDING_MODEL
                    record.embedding_version = EMBEDDING_VERSION
                    backfilled += 1
        return backfilled

    async def search(
        self,
        tenant_id: str,
        query: str,
        limit: int = 5,
        mode: str = "hybrid",
        fts_weight: float = 0.5,
        vector_weight: float = 0.5,
    ) -> list[RetrievedChunk]:
        query_vector = self._embedder.embed(query)
        async with self._session_factory() as session:
            dialect = session.get_bind().dialect.name
            if dialect == "postgresql":
                keyword_scores, vector_scores, chunks_by_id = await self._search_postgres(
                    session, tenant_id, query, query_vector
                )
            else:
                keyword_scores, vector_scores, chunks_by_id = await self._search_backport(
                    session, tenant_id, query, query_vector
                )

        if mode == "keyword":
            vector_scores = {key: 0.0 for key in vector_scores}
        elif mode == "vector":
            keyword_scores = {key: 0.0 for key in keyword_scores}

        fused = fuse_scores(keyword_scores, vector_scores, fts_weight, vector_weight)
        remaining = {key: value for key, value in fused.items() if key in chunks_by_id}
        results = merge_retrieved_chunks(chunks_by_id, remaining, mode)
        return results[:limit]

    async def _search_postgres(
        self,
        session: AsyncSession,
        tenant_id: str,
        query: str,
        query_vector: list[float],
    ) -> tuple[dict[str, float], dict[str, float], dict[str, RetrievedChunk]]:
        # 路径 1：PostgreSQL FTS rank
        fts_doc = func.to_tsvector("english", KnowledgeChunkRecord.content)
        fts_query = func.plainto_tsquery("english", query)
        fts_row = select(
            KnowledgeChunkRecord.chunk_id,
            func.ts_rank(fts_doc, fts_query).label("fts_score"),
        ).where(
            KnowledgeChunkRecord.tenant_id == tenant_id,
            fts_doc.op("@@")(fts_query),
        )
        keyword_scores: dict[str, float] = {}
        for chunk_id, score in (await session.execute(fts_row)).all():
            keyword_scores[chunk_id] = float(score)

        # 路径 2：pgvector 余弦相似度（1 - cosine_distance）
        vector_rows = (
            select(
                KnowledgeChunkRecord.chunk_id,
                (1.0 - KnowledgeChunkRecord.embedding.cosine_distance(query_vector)).label(
                    "vec_score"
                ),
            )
            .where(
                KnowledgeChunkRecord.tenant_id == tenant_id,
                KnowledgeChunkRecord.embedding.is_not(None),
            )
            .order_by(KnowledgeChunkRecord.embedding.cosine_distance(query_vector))
        )
        vector_scores: dict[str, float] = {}
        for chunk_id, score in (await session.execute(vector_rows)).all():
            vector_scores[chunk_id] = float(score)

        chunks_by_id = await self._load_candidates(
            session, tenant_id, set(keyword_scores) | set(vector_scores)
        )
        return keyword_scores, vector_scores, chunks_by_id

    async def _search_backport(
        self,
        session: AsyncSession,
        tenant_id: str,
        query: str,
        query_vector: list[float],
    ) -> tuple[dict[str, float], dict[str, float], dict[str, RetrievedChunk]]:
        from agentforge.platform.application.knowledge_embedder import cosine_similarity

        terms = [term for term in query.split() if len(term) > 2]
        predicates = []
        for term in terms:
            pattern = f"%{term}%"
            predicates.extend(
                [
                    KnowledgeChunkRecord.content.ilike(pattern),
                    KnowledgeDocumentRecord.title.ilike(pattern),
                ]
            )
        statement = (
            select(KnowledgeChunkRecord, KnowledgeDocumentRecord)
            .join(
                KnowledgeDocumentRecord,
                KnowledgeChunkRecord.document_id == KnowledgeDocumentRecord.document_id,
            )
            .where(KnowledgeChunkRecord.tenant_id == tenant_id)
        )
        if predicates:
            statement = statement.where(or_(*predicates))

        keyword_scores: dict[str, float] = {}
        vector_scores: dict[str, float] = {}
        chunks_by_id: dict[str, RetrievedChunk] = {}
        for chunk, document in (await session.execute(statement)).all():
            el = chunk.embedding if chunk.embedding is not None else []
            vec_score = cosine_similarity(query_vector, list(el)) if el else 0.0
            kw_score = 0.0
            if terms:
                haystack = f"{document.title} {chunk.content}".lower()
                kw_score = sum(1.0 for term in terms if term in haystack) / len(terms)
            keyword_scores[chunk.chunk_id] = kw_score
            vector_scores[chunk.chunk_id] = vec_score
            chunks_by_id[chunk.chunk_id] = RetrievedChunk(
                chunk_id=chunk.chunk_id,
                document_id=document.document_id,
                tenant_id=chunk.tenant_id,
                title=document.title,
                content=chunk.content,
                score=0.0,
                source_uri=document.source_uri,
                fts_score=kw_score,
                vector_score=vec_score,
            )
        return keyword_scores, vector_scores, chunks_by_id

    async def _load_candidates(
        self,
        session: AsyncSession,
        tenant_id: str,
        chunk_ids: set[str],
    ) -> dict[str, RetrievedChunk]:
        if not chunk_ids:
            return {}
        statement = (
            select(KnowledgeChunkRecord, KnowledgeDocumentRecord)
            .join(
                KnowledgeDocumentRecord,
                KnowledgeChunkRecord.document_id == KnowledgeDocumentRecord.document_id,
            )
            .where(
                KnowledgeChunkRecord.tenant_id == tenant_id,
                KnowledgeChunkRecord.chunk_id.in_(list(chunk_ids)),
            )
        )
        chunks_by_id: dict[str, RetrievedChunk] = {}
        for chunk, document in (await session.execute(statement)).all():
            chunks_by_id[chunk.chunk_id] = RetrievedChunk(
                chunk_id=chunk.chunk_id,
                document_id=document.document_id,
                tenant_id=chunk.tenant_id,
                title=document.title,
                content=chunk.content,
                score=0.0,
                source_uri=document.source_uri,
            )
        return chunks_by_id
