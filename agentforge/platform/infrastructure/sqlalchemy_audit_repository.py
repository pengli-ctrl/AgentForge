"""AgentForge 平台基础设施层：sqlalchemy_audit_repository。

本模块提供 sqlalchemy_audit_repository 的数据库持久化实现，负责事务、查询、租户隔离和一致性约束。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：SQLAlchemyAuditRepository。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.infrastructure.db.models import AuditEventRecord


class SQLAlchemyAuditRepository:
    """SQLAlchemyAuditRepository。

    SQLAlchemyAuditRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 save()。
    - 方法 list_events()。
    - 方法 query_events()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            session_factory: async_sessionmaker[AsyncSession]，调用方传入的 session_factory 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._session_factory = session_factory

    async def save(self, event: AuditEvent) -> None:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            event: AuditEvent，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。
            resource_id: str | None，调用方传入的 resource_id 参数。

        Returns:
            list[AuditEvent]，函数执行后的结果。
        """
        statement = select(AuditEventRecord).where(AuditEventRecord.tenant_id == tenant_id)
        if resource_id is not None:
            statement = statement.where(AuditEventRecord.resource_id == resource_id)
        statement = statement.order_by(AuditEventRecord.created_at.desc()).limit(limit)
        async with self._session_factory() as session:
            records = (await session.execute(statement)).scalars().all()
        return [record.to_domain() for record in records]

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
        """执行查询并返回结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            action: str | None，调用方传入的 action 参数。
            actor_id: str | None，调用方传入的 actor_id 参数。
            resource_id: str | None，调用方传入的 resource_id 参数。
            resource_type: str | None，调用方传入的 resource_type 参数。
            limit: int，调用方传入的 limit 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            tuple[list[AuditEvent], str | None]，函数执行后的结果。
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
