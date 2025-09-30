from __future__ import annotations

from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.ticket import Ticket


class MemoryTicketRepository:
    def __init__(self) -> None:
        self._by_id: dict[tuple[str, str], Ticket] = {}
        self._by_idempotency: dict[tuple[str, str], str] = {}
        self.outbox: list[EventEnvelope] = []

    async def get(self, tenant_id: str, ticket_id: str) -> Ticket | None:
        return self._by_id.get((tenant_id, ticket_id))

    async def save(
        self,
        ticket: Ticket,
        events: list[EventEnvelope] | None = None,
    ) -> Ticket:
        self._by_id[(ticket.tenant_id, ticket.ticket_id)] = ticket
        self._by_idempotency[(ticket.tenant_id, ticket.idempotency_key)] = ticket.ticket_id
        if events:
            self.outbox.extend(events)
        return ticket

    async def get_by_idempotency_key(self, tenant_id: str, idempotency_key: str) -> Ticket | None:
        ticket_id = self._by_idempotency.get((tenant_id, idempotency_key))
        if ticket_id is None:
            return None
        return self._by_id.get((tenant_id, ticket_id))

    async def list(
        self,
        tenant_id: str,
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[Ticket], str | None]:
        tickets = [
            t
            for (t_tenant, _t_id), t in self._by_id.items()
            if t_tenant == tenant_id and (status is None or t.status == status)
        ]
        tickets.sort(key=lambda t: t.created_at)
        start = int(cursor) if (cursor is not None and cursor.isdigit()) else 0
        bucket = tickets[start : start + limit]
        next_cursor = str(start + len(bucket)) if start + len(bucket) < len(tickets) else None
        return bucket, next_cursor
