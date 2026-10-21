"""SQLAlchemy审计仓储模块。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.infrastructure.db.models import AuditEventRecord


class SQLAlchemyAuditRepository:
    """审计仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyAuditRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save(self, event: AuditEvent) -> None:
        """保存审计。

        Args:
            event: 待处理事件。
        """
        async with self._session_factory() as session:
            session.add(AuditEventRecord.from_domain(event))
            await session.commit()

    async def list_events(
        self,
        tenant_id: str,
        limit: int = 100,
        resource_id: str | None = None,
    ) -> list[AuditEvent]:
        """查询事件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。
            resource_id: 资源 ID。

        Returns:
            结果列表。
        """
        statement = select(AuditEventRecord).where(AuditEventRecord.tenant_id == tenant_id)
        if resource_id is not None:
            statement = statement.where(AuditEventRecord.resource_id == resource_id)
        statement = statement.order_by(AuditEventRecord.created_at.desc()).limit(limit)
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

    async def delete_events_before(self, tenant_id: str, before: datetime) -> int:
        """删除事件之前。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            before: 之前。

        Returns:
            整数结果。
        """
        async with self._session_factory() as session:
            result = await session.execute(
                delete(AuditEventRecord).where(
                    AuditEventRecord.tenant_id == tenant_id,
                    AuditEventRecord.created_at < before,
                )
            )
            await session.commit()
            return int(getattr(result, "rowcount", 0) or 0)

    async def query_events(
        self,
        tenant_id: str | None = None,
        action: str | None = None,
        actor_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[AuditEvent], str | None]:
        """查询事件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            action: 待执行动作名称。
            actor_id: 执行操作的参与者 ID。
            resource_id: 资源 ID。
            resource_type: 资源类型。
            limit: 返回记录的最大数量。
            cursor: 分页游标。

        Returns:
            结果元组。
        """
        statement = select(AuditEventRecord)
        if tenant_id is not None:
            statement = statement.where(AuditEventRecord.tenant_id == tenant_id)
        if action is not None:
            statement = statement.where(AuditEventRecord.action == action)
        if actor_id is not None:
            statement = statement.where(AuditEventRecord.actor_id == actor_id)
        if resource_id is not None:
            statement = statement.where(AuditEventRecord.resource_id == resource_id)
        if resource_type is not None:
            statement = statement.where(AuditEventRecord.resource_type == resource_type)
        statement = statement.order_by(AuditEventRecord.created_at.desc())
        start = int(cursor) if (cursor is not None and cursor.isdigit()) else 0
        async with self._session_factory() as session:
            rows = (await session.execute(statement.offset(start).limit(limit + 1))).scalars().all()
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = str(start + len(page)) if has_more else None
        return [record.to_domain() for record in page], next_cursor
