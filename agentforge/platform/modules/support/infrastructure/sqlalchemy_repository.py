"""SQLAlchemy仓储模块。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.infrastructure.db.models import OutboxEventRecord
from agentforge.platform.modules.support.domain.ticket import Ticket, TicketStatus
from agentforge.platform.modules.support.infrastructure.models import TicketRecord


class SQLAlchemyTicketRepository:
    """工单仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyTicketRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def get(self, tenant_id: str, ticket_id: str) -> Ticket | None:
        """读取工单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            ticket_id: 工单 ID。

        Returns:
            工单无结果。
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
        """保存工单。

        Args:
            ticket: 客服工单对象。
            events: 事件。

        Returns:
            工单结果。
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
        """获取由键。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            idempotency_key: 幂等键，用于避免重复处理。

        Returns:
            工单无结果。
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
        assigned_team: str | None = None,
        assignee_id: str | None = None,
        queue: str | None = None,
        overdue: bool = False,
        due_before: str | None = None,
    ) -> tuple[list[Ticket], str | None]:
        """查询工单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            status: 目标状态。
            limit: 返回记录的最大数量。
            cursor: 分页游标。
            assigned_team: 输入参数。
            assignee_id: 处理人 ID。
            queue: 队列。
            overdue: 逾期。
            due_before: 到期之前。

        Returns:
            结果元组。
        """
        async with self._session_factory() as session:
            statement = select(TicketRecord).where(TicketRecord.tenant_id == tenant_id)
            if status is not None:
                statement = statement.where(TicketRecord.status == status)
            if assigned_team is not None:
                statement = statement.where(TicketRecord.assigned_team == assigned_team)
            if assignee_id is not None:
                statement = statement.where(TicketRecord.assignee_id == assignee_id)
            if queue is not None:
                statement = statement.where(TicketRecord.payload["queue"].as_string() == queue)
            if overdue or due_before is not None:
                due_at = TicketRecord.payload["sla"]["due_at"].as_string()
                statement = statement.where(
                    TicketRecord.status.notin_(
                        [TicketStatus.PUBLISHED.value, TicketStatus.CANCELLED.value]
                    )
                )
                if overdue:
                    statement = statement.where(due_at < datetime.now(timezone.utc).isoformat())
                if due_before is not None:
                    statement = statement.where(due_at <= due_before)
            statement = statement.order_by(TicketRecord.created_at.asc())
            start = int(cursor) if (cursor is not None and cursor.isdigit()) else 0
            rows = (await session.execute(statement.offset(start).limit(limit + 1))).scalars().all()
            has_more = len(rows) > limit
            page = rows[:limit]
            next_cursor = str(start + len(page)) if has_more else None
            return [r.to_domain() for r in page], next_cursor

    async def list_all(self, limit: int = 10_000) -> Sequence[Ticket]:
        """查询全部。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        statement = (
            select(TicketRecord)
            .order_by(
                TicketRecord.created_at.desc(),
                TicketRecord.ticket_id.desc(),
            )
            .limit(limit)
        )
        async with self._session_factory() as session:
            rows = list((await session.execute(statement)).scalars().all())
        return [row.to_domain() for row in rows]
