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

    async def list_events(
        self,
        tenant_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[dict], str | None]:
        async with self._session_factory() as session:
            statement = select(OutboxEventRecord)
            if tenant_id is not None:
                statement = statement.where(OutboxEventRecord.tenant_id == tenant_id)
            if status is not None:
                statement = statement.where(OutboxEventRecord.status == status)
            statement = statement.order_by(OutboxEventRecord.created_at.asc())
            start = int(cursor) if (cursor is not None and cursor.isdigit()) else 0
            rows = (await session.execute(statement.offset(start).limit(limit + 1))).scalars().all()
            has_more = len(rows) > limit
            page = rows[:limit]
            next_cursor = str(start + len(page)) if has_more else None
            return (
                [self._to_summary(r) for r in page],
                next_cursor,
            )

    async def get_event(self, tenant_id: str | None, event_id: str) -> dict | None:
        async with self._session_factory() as session:
            record = await session.get(OutboxEventRecord, event_id)
            if record is None:
                return None
            if tenant_id is not None and record.tenant_id != tenant_id:
                return None
            return {
                "event_id": record.event_id,
                "tenant_id": record.tenant_id,
                "event_type": record.event_type,
                "status": record.status,
                "attempts": record.attempts,
                "last_error": record.last_error,
                "payload": record.payload,
                "created_at": record.created_at.isoformat(),
                "published_at": record.published_at.isoformat() if record.published_at else None,
            }

    async def count_events(self, tenant_id: str | None = None) -> dict[str, int]:
        async with self._session_factory() as session:
            from sqlalchemy import func

            statement = select(OutboxEventRecord.status, func.count()).group_by(
                OutboxEventRecord.status
            )
            if tenant_id is not None:
                statement = statement.where(OutboxEventRecord.tenant_id == tenant_id)
            rows = (await session.execute(statement)).all()
            counts = {row[0]: row[1] for row in rows}
            return {
                "pending": counts.get("pending", 0),
                "published": counts.get("published", 0),
                "failed": counts.get("failed", 0),
                "discarded": counts.get("discarded", 0),
            }

    async def discard(self, tenant_id: str | None, event_id: str) -> bool:
        async with self._session_factory() as session:
            record = await session.get(OutboxEventRecord, event_id)
            if record is None:
                return False
            if tenant_id is not None and record.tenant_id != tenant_id:
                return False
            record.status = "discarded"
            if not record.last_error:
                record.last_error = "discarded by operator"
            await session.commit()
            return True

    @staticmethod
    def _to_summary(record) -> dict:
        return {
            "event_id": record.event_id,
            "tenant_id": record.tenant_id,
            "event_type": record.event_type,
            "status": record.status,
            "attempts": record.attempts,
            "last_error": record.last_error,
            "created_at": record.created_at.isoformat(),
            "published_at": record.published_at.isoformat() if record.published_at else None,
        }

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
