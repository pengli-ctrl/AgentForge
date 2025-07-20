from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.infrastructure.db.models import OutboxEventRecord


class SQLAlchemyOutboxStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        max_attempts: int = 5,
    ) -> None:
        self._session_factory = session_factory
        self._max_attempts = max_attempts

    async def fetch_pending(self, limit: int = 100) -> list[EventEnvelope]:
        async with self._session_factory() as session:
            statement = (
                select(OutboxEventRecord)
                .where(OutboxEventRecord.status == "pending")
                .order_by(OutboxEventRecord.created_at)
                .limit(limit)
            )
            records = (await session.execute(statement)).scalars().all()
            return [EventEnvelope.model_validate(record.payload) for record in records]

    async def mark_published(self, event_id: str) -> None:
        async with self._session_factory() as session:
            record = await session.get(OutboxEventRecord, event_id)
            if record is None:
                return
            record.status = "published"
            record.published_at = datetime.now(timezone.utc)
            await session.commit()

    async def mark_failed(self, event_id: str, error: str) -> None:
        async with self._session_factory() as session:
            record = await session.get(OutboxEventRecord, event_id)
            if record is None:
                return
            record.attempts += 1
            record.last_error = error[:2000]
            if record.attempts >= self._max_attempts:
                record.status = "failed"
            await session.commit()

    async def list_failed(self, limit: int = 100) -> list[dict]:
        async with self._session_factory() as session:
            statement = (
                select(OutboxEventRecord)
                .where(OutboxEventRecord.status == "failed")
                .order_by(OutboxEventRecord.created_at)
                .limit(limit)
            )
            records = (await session.execute(statement)).scalars().all()
            return [
                {
                    "event_id": record.event_id,
                    "event_type": record.event_type,
                    "attempts": record.attempts,
                    "last_error": record.last_error,
                    "payload": record.payload,
                }
                for record in records
            ]

    async def replay(self, event_id: str) -> bool:
        async with self._session_factory() as session:
            record = await session.get(OutboxEventRecord, event_id)
            if record is None:
                return False
            record.status = "pending"
            record.attempts = 0
            record.last_error = None
            await session.commit()
            return True
