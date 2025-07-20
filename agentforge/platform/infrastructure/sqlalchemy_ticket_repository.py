from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.ticket import Ticket
from agentforge.platform.infrastructure.db.models import OutboxEventRecord, TicketRecord


class SQLAlchemyTicketRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, tenant_id: str, ticket_id: str) -> Ticket | None:
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
        async with self._session_factory() as session:
            statement = select(TicketRecord).where(
                TicketRecord.tenant_id == tenant_id,
                TicketRecord.idempotency_key == idempotency_key,
            )
            record = (await session.execute(statement)).scalar_one_or_none()
            return record.to_domain() if record is not None else None
