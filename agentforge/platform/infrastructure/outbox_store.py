"""AgentForge 平台基础设施层：outbox_store。

本模块实现 outbox_store 的持久化接口，隔离业务逻辑与具体存储细节。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：SQLAlchemyOutboxStore。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.infrastructure.db.models import OutboxEventRecord


class SQLAlchemyOutboxStore:
    """SQLAlchemyOutboxStore。

    SQLAlchemyOutboxStore 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 fetch_pending()。
    - 方法 mark_published()。
    - 方法 mark_failed()。
    - 方法 list_failed()。
    - 方法 list_events()。
    - 方法 get_event()。
    - 方法 count_events()。
    - 方法 discard()。
    - 方法 replay()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        max_attempts: int = 5,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            session_factory: async_sessionmaker[AsyncSession]，调用方传入的 session_factory 参数。
            max_attempts: int，调用方传入的 max_attempts 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._session_factory = session_factory
        self._max_attempts = max_attempts

    async def fetch_pending(self, limit: int = 100) -> list[EventEnvelope]:
        """从外部或内部来源获取数据，并返回调用方需要的结果。

        Args:
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[EventEnvelope]，函数执行后的结果。
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
        """执行 mark_published 对应的逻辑，并返回处理结果。

        Args:
            event_id: str，调用方传入的 event_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        async with self._session_factory() as session:
            record = await session.get(OutboxEventRecord, event_id)
            if record is None:
                return
            record.status = "published"
            record.published_at = datetime.now(timezone.utc)
            await session.commit()

    async def mark_failed(self, event_id: str, error: str) -> None:
        """执行 mark_failed 对应的逻辑，并返回处理结果。

        Args:
            event_id: str，调用方传入的 event_id 参数。
            error: str，调用方传入的 error 参数。

        Returns:
            None，函数执行后的结果。
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

    async def list_failed(self, limit: int = 100) -> list[dict]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[dict]，函数执行后的结果。
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            status: str | None，调用方传入的 status 参数。
            limit: int，调用方传入的 limit 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            tuple[list[dict], str | None]，函数执行后的结果。
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
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            event_id: str，调用方传入的 event_id 参数。

        Returns:
            dict | None，函数执行后的结果。
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
        """执行 count_events 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。

        Returns:
            dict[str, int]，函数执行后的结果。
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
        """执行 discard 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            event_id: str，调用方传入的 event_id 参数。

        Returns:
            bool，函数执行后的结果。
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
        """执行 _to_summary 对应的逻辑，并返回处理结果。

        Args:
            record: Any，调用方传入的 record 参数。

        Returns:
            dict，函数执行后的结果。
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
        """执行 replay 对应的逻辑，并返回处理结果。

        Args:
            event_id: str，调用方传入的 event_id 参数。

        Returns:
            bool，函数执行后的结果。
        """
        async with self._session_factory() as session:
            record = await session.get(OutboxEventRecord, event_id)
            if record is None:
                return False
            record.status = "pending"
            record.attempts = 0
            record.last_error = None
            await session.commit()
            return True
