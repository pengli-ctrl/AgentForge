"""Outbox存储模块。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.infrastructure.db.models import (
    OutboxEventRecord,
    OutboxHandlerReceiptRecord,
)


class SQLAlchemyOutboxStore:
    """Outbox相关组件。"""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        max_attempts: int = 5,
    ) -> None:
        """初始化 SQLAlchemyOutboxStore。

        Args:
            session_factory: 数据库会话工厂。
            max_attempts: 最大。
        """
        self._session_factory = session_factory
        self._max_attempts = max_attempts

    async def enqueue(self, event: EventEnvelope) -> None:
        """写入队列Outbox。

        Args:
            event: 待处理事件。
        """
        async with self._session_factory() as session:
            await session.merge(OutboxEventRecord.from_event(event))
            await session.commit()

    async def fetch_pending(self, limit: int = 100) -> list[EventEnvelope]:
        """获取待处理。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
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
        """标记已发布。

        Args:
            event_id: 事件 ID。
        """
        async with self._session_factory() as session:
            record = await session.get(OutboxEventRecord, event_id)
            if record is None:
                return
            record.status = "published"
            record.published_at = datetime.now(timezone.utc)
            await session.commit()

    async def mark_failed(self, event_id: str, error: str) -> None:
        """标记失败。

        Args:
            event_id: 事件 ID。
            error: 错误。
        """
        async with self._session_factory() as session:
            record = await session.get(OutboxEventRecord, event_id)
            if record is None:
                return
            record.attempts += 1
            record.last_error = error[:2000]
            if record.attempts >= self._max_attempts:
                record.status = "failed"
            await session.commit()

    async def claim_handler(
        self,
        event_id: str,
        handler_name: str,
        *,
        lease_seconds: int = 60,
    ) -> str:
        """处理报销单处理器。

        Args:
            event_id: 事件 ID。
            handler_name: 处理器名称。
            lease_seconds: 输入参数。

        Returns:
            字符串结果。
        """
        now = datetime.now(timezone.utc)
        async with self._session_factory() as session:
            record = await session.get(OutboxHandlerReceiptRecord, (event_id, handler_name))
            if record is None:
                session.add(
                    OutboxHandlerReceiptRecord(
                        event_id=event_id,
                        handler_name=handler_name,
                        status="processing",
                        claimed_at=now,
                    )
                )
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    return "busy"
                return "claimed"
            if record.status == "completed":
                return "completed"
            claimed_at = record.claimed_at
            if claimed_at.tzinfo is None:
                claimed_at = claimed_at.replace(tzinfo=timezone.utc)
            lease_start = now - timedelta(seconds=lease_seconds)
            if record.status == "processing" and claimed_at > lease_start:
                return "busy"
            record.status = "processing"
            record.claimed_at = now
            record.last_error = None
            await session.commit()
            return "claimed"

    async def complete_handler(self, event_id: str, handler_name: str) -> None:
        """完成处理器。

        Args:
            event_id: 事件 ID。
            handler_name: 处理器名称。
        """
        async with self._session_factory() as session:
            record = await session.get(OutboxHandlerReceiptRecord, (event_id, handler_name))
            if record is None:
                return
            record.status = "completed"
            record.processed_at = datetime.now(timezone.utc)
            record.last_error = None
            await session.commit()

    async def release_handler(self, event_id: str, handler_name: str, error: str = "") -> None:
        """处理释放处理器。

        Args:
            event_id: 事件 ID。
            handler_name: 处理器名称。
            error: 错误。
        """
        async with self._session_factory() as session:
            record = await session.get(OutboxHandlerReceiptRecord, (event_id, handler_name))
            if record is None or record.status == "completed":
                return
            if error:
                record.status = "failed"
                record.last_error = error[:2000]
                await session.commit()
                return
            await session.delete(record)
            await session.commit()

    async def list_failed(self, limit: int = 100) -> list[dict]:
        """查询失败。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
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
        """查询事件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            status: 目标状态。
            limit: 返回记录的最大数量。
            cursor: 分页游标。

        Returns:
            结果元组。
        """
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
        """读取事件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            event_id: 事件 ID。

        Returns:
            结构化结果字典。
        """
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
        """统计事件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
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
        """判断丢弃是否成立。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            event_id: 事件 ID。

        Returns:
            操作是否成功。
        """
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
        """将 Outbox 记录转换为摘要响应。

        Args:
            record: 待处理的领域记录。

        Returns:
            结构化结果字典。
        """
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
        """重放Outbox。

        Args:
            event_id: 事件 ID。

        Returns:
            操作是否成功。
        """
        async with self._session_factory() as session:
            record = await session.get(OutboxEventRecord, event_id)
            if record is None:
                return False
            record.status = "pending"
            record.attempts = 0
            record.last_error = None
            await session.execute(
                delete(OutboxHandlerReceiptRecord).where(
                    OutboxHandlerReceiptRecord.event_id == event_id
                )
            )
            await session.commit()
            return True
