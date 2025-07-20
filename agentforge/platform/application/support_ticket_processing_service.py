from __future__ import annotations

from typing import Any
from uuid import uuid4

from agentforge.platform.application.knowledge_service import KnowledgeService
from agentforge.platform.application.ports import AuditRepository, CostRepository, TicketRepository
from agentforge.platform.application.reply_draft_service import ReplyDraftService
from agentforge.platform.application.support_ticket_service import SupportTicketService
from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.cost import CostRecord
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.ticket import Ticket, TicketStatus
from agentforge.platform.observability.tracing import start_span


class SupportTicketProcessingService:
    def __init__(
        self,
        ticket_service: SupportTicketService,
        ticket_repository: TicketRepository,
        knowledge_service: KnowledgeService,
        reply_draft_service: ReplyDraftService,
        cost_repository: CostRepository,
        audit_repository: AuditRepository | None = None,
    ) -> None:
        self._ticket_service = ticket_service
        self._ticket_repository = ticket_repository
        self._knowledge_service = knowledge_service
        self._reply_draft_service = reply_draft_service
        self._cost_repository = cost_repository
        self._audit_repository = audit_repository

    async def process_event(self, event: dict[str, Any]) -> Ticket:
        with start_span("support_ticket.process") as span:
            if span and span.is_recording():
                span.set_attribute("tenant_id", str(event.get("tenant_id", "")))
            return await self._process_event(event, span)

    async def _process_event(self, event: dict[str, Any], span) -> Ticket:
        ticket = await self._ticket_service.create_from_event(event)
        chunks = await self._knowledge_service.search(ticket.tenant_id, ticket.subject, limit=5)
        draft = await self._reply_draft_service.create_draft(ticket, chunks)
        ticket.metadata["retrieval"] = [chunk.model_dump(mode="json") for chunk in chunks]
        ticket.metadata["draft"] = draft.model_dump(mode="json")

        if draft.requires_approval and ticket.status == TicketStatus.WAITING_REVIEW:
            ticket.transition_to(TicketStatus.WAITING_APPROVAL)

        trace_id = str(uuid4())
        event_envelope = EventEnvelope(
            event_id=str(uuid4()),
            event_type="ticket.drafted",
            tenant_id=ticket.tenant_id,
            task_id=ticket.ticket_id,
            trace_id=trace_id,
            producer="support-ticket-processing-service",
            payload={
                "ticket_id": ticket.ticket_id,
                "citation_count": len(draft.citations),
                "requires_approval": draft.requires_approval,
            },
        )
        await self._ticket_repository.save(ticket, events=[event_envelope])

        if self._audit_repository is not None:
            await self._audit_repository.save(
                AuditEvent(
                    event_id=str(uuid4()),
                    tenant_id=ticket.tenant_id,
                    action="ticket.drafted",
                    resource_type="ticket",
                    resource_id=ticket.ticket_id,
                    risk_level=ticket.risk_level,
                    actor_id="support-ticket-processing-service",
                    trace_id=trace_id,
                    payload={
                        "citation_count": len(draft.citations),
                        "requires_approval": draft.requires_approval,
                        "model_name": draft.model_name,
                        "provider": draft.provider,
                        "cost_amount": draft.cost_amount,
                    },
                )
            )

        if draft.model_name:
            await self._cost_repository.save(
                CostRecord(
                    tenant_id=ticket.tenant_id,
                    task_id=ticket.ticket_id,
                    model_name=draft.model_name,
                    provider=draft.provider,
                    input_tokens=draft.input_tokens,
                    output_tokens=draft.output_tokens,
                    amount=draft.cost_amount,
                )
            )
        if span and span.is_recording():
            span.set_attribute("task_id", ticket.ticket_id)
            span.set_attribute("ticket_status", ticket.status.value)
            span.set_attribute("citation_count", len(draft.citations))
            span.set_attribute("model_name", draft.model_name)
            span.set_attribute("cost_amount", draft.cost_amount)
        return ticket
