"""AgentForge 平台基础设施层：sqlalchemy_ticket_repository。

本模块提供 sqlalchemy_ticket_repository 的数据库持久化实现，负责事务、查询、租户隔离和一致性约束。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：SQLAlchemyTicketRepository。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.ticket import Ticket
from agentforge.platform.infrastructure.db.models import OutboxEventRecord, TicketRecord


class SQLAlchemyTicketRepository:
    """SQLAlchemyTicketRepository。

    SQLAlchemyTicketRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 get()。
    - 方法 save()。
    - 方法 get_by_idempotency_key()。
    - 方法 list()。

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

    async def get(self, tenant_id: str, ticket_id: str) -> Ticket | None:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            ticket_id: str，调用方传入的 ticket_id 参数。

        Returns:
            Ticket | None，函数执行后的结果。
        """
        async with self._session_factory() as session:
            record = await session.get(TicketRecord, ticket_id)
            if record is None or record.tenant_id != tenant_id:
                return None
            return record.to_domain()

    async def save(
        self,
        ticket: Ticket,
        events: list[EventEnvelope] | None = None,
    ) -> Ticket:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            ticket: Ticket，调用方传入的 ticket 参数。
            events: list[EventEnvelope] | None，调用方传入的 events 参数。

        Returns:
            Ticket，函数执行后的结果。
        """
        async with self._session_factory() as session:
            async with session.begin():
                record = await session.get(TicketRecord, ticket.ticket_id)
                if record is None:
                    record = TicketRecord.from_domain(ticket)
                    session.add(record)
                else:
                    record.apply_domain(ticket)
                for event in events or []:
                    session.add(OutboxEventRecord.from_event(event))
            return record.to_domain()

    async def get_by_idempotency_key(self, tenant_id: str, idempotency_key: str) -> Ticket | None:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            idempotency_key: str，调用方传入的 idempotency_key 参数。

        Returns:
            Ticket | None，函数执行后的结果。
        """
        async with self._session_factory() as session:
            statement = select(TicketRecord).where(
                TicketRecord.tenant_id == tenant_id,
                TicketRecord.idempotency_key == idempotency_key,
            )
            record = (await session.execute(statement)).scalar_one_or_none()
            return record.to_domain() if record is not None else None

    async def list(
        self,
        tenant_id: str,
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[Ticket], str | None]:
        """执行 list 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            status: str | None，调用方传入的 status 参数。
            limit: int，调用方传入的 limit 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            tuple[list[Ticket], str | None]，函数执行后的结果。
        """
        async with self._session_factory() as session:
            statement = select(TicketRecord).where(TicketRecord.tenant_id == tenant_id)
            if status is not None:
                statement = statement.where(TicketRecord.status == status)
            statement = statement.order_by(TicketRecord.created_at.asc())
            start = int(cursor) if (cursor is not None and cursor.isdigit()) else 0
            rows = (await session.execute(statement.offset(start).limit(limit + 1))).scalars().all()
            has_more = len(rows) > limit
            page = rows[:limit]
            next_cursor = str(start + len(page)) if has_more else None
            return [r.to_domain() for r in page], next_cursor
