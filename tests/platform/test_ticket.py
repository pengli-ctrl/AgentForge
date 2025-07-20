import pytest

from agentforge.platform.domain.ticket import Ticket, TicketStatus
from agentforge.platform.infrastructure.memory_ticket_repository import MemoryTicketRepository


def make_ticket() -> Ticket:
    return Ticket(
        ticket_id="ticket-1",
        tenant_id="tenant-1",
        source="feishu",
        idempotency_key="event-1",
    )


def test_ticket_valid_transition() -> None:
    ticket = make_ticket()
    ticket.transition_to(TicketStatus.CLASSIFYING)
    ticket.transition_to(TicketStatus.WAITING_REVIEW)
    assert ticket.status == TicketStatus.WAITING_REVIEW
    assert ticket.version == 3


def test_ticket_rejects_invalid_transition() -> None:
    ticket = make_ticket()
    with pytest.raises(ValueError):
        ticket.transition_to(TicketStatus.PUBLISHED)


@pytest.mark.asyncio
async def test_idempotent_repository_lookup() -> None:
    repo = MemoryTicketRepository()
    ticket = make_ticket()
    await repo.save(ticket)
    found = await repo.get_by_idempotency_key("tenant-1", "event-1")
    assert found is not None
    assert found.ticket_id == "ticket-1"
