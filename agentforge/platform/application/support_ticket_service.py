from __future__ import annotations

from typing import Any
from uuid import uuid4

from agentforge.platform.application.classifier import RuleBasedTicketClassifier
from agentforge.platform.application.ports import (
    AuditRepository,
    EvaluationRepository,
    TicketRepository,
)
from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.evaluation import EvaluationSample
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.ticket import RiskLevel, Ticket, TicketStatus


class SupportTicketService:
    def __init__(
        self,
        repository: TicketRepository,
        classifier: RuleBasedTicketClassifier,
        reply_connector=None,
        audit_repository: AuditRepository | None = None,
        evaluation_repository: EvaluationRepository | None = None,
    ) -> None:
        self._repository = repository
        self._classifier = classifier
        self._reply_connector = reply_connector
        self._audit_repository = audit_repository
        self._evaluation_repository = evaluation_repository

    async def create_from_event(self, event: dict[str, Any]) -> Ticket:
        tenant_id = self._require(event, "tenant_id")
        source = self._require(event, "source")
        message_id = self._require(event, "message_id")
        text = self._require(event, "text")
        existing = await self._repository.get_by_idempotency_key(tenant_id, message_id)
        if existing is not None:
            return existing
        ticket = Ticket(
            ticket_id=str(uuid4()),
            tenant_id=tenant_id,
            customer_id=event.get("customer_id"),
            conversation_id=event.get("conversation_id") or event.get("reply_target"),
            source=source,
            subject=text[:120],
            idempotency_key=message_id,
            metadata={
                "message_id": message_id,
                "raw_message": text,
                "reply_target": event.get("reply_target"),
            },
        )
        ticket.transition_to(TicketStatus.CLASSIFYING)
        result = await self._classifier.classify(text)
        ticket.intent = result.intent
        ticket.priority = result.priority
        ticket.product = result.product
        ticket.assigned_team = result.assigned_team
        ticket.risk_level = result.risk_level
        ticket.confidence = result.confidence
        if result.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            ticket.transition_to(TicketStatus.WAITING_APPROVAL)
        else:
            ticket.transition_to(TicketStatus.WAITING_REVIEW)
        trace_id = str(uuid4())
        await self._repository.save(
            ticket,
            events=[self._make_event("ticket.created", ticket, trace_id)],
        )
        await self._record_audit(
            action="ticket.created",
            ticket=ticket,
            actor_type="system",
            actor_id="support-ticket-service",
            trace_id=trace_id,
            payload={"source": source, "status": ticket.status.value},
        )
        return ticket

    async def apply_approval(
        self, tenant_id: str, ticket_id: str, decision: str, decided_by: str
    ) -> Ticket:
        ticket = await self._repository.get(tenant_id, ticket_id)
        if ticket is None:
            raise ValueError("Ticket not found")
        if decision not in {"approve", "reject"}:
            raise ValueError("Unsupported approval decision")
        if decision == "approve" and ticket.status == TicketStatus.READY_TO_PUBLISH:
            return ticket
        if decision == "reject" and ticket.status == TicketStatus.ESCALATED:
            return ticket
        if ticket.status != TicketStatus.WAITING_APPROVAL:
            raise ValueError("Ticket is not waiting for approval")
        if decision == "approve":
            ticket.transition_to(TicketStatus.READY_TO_PUBLISH)
        else:
            ticket.transition_to(TicketStatus.ESCALATED)
        ticket.metadata["approval"] = {"decision": decision, "decided_by": decided_by}
        trace_id = str(uuid4())
        await self._repository.save(
            ticket,
            events=[self._make_event("approval.completed", ticket, trace_id)],
        )
        await self._record_audit(
            action="approval.completed",
            ticket=ticket,
            actor_type="user",
            actor_id=decided_by,
            trace_id=trace_id,
            payload={"decision": decision, "status": ticket.status.value},
        )
        return ticket

    async def review_draft(
        self,
        tenant_id: str,
        ticket_id: str,
        action: str,
        reviewer_id: str,
        edited_text: str | None = None,
        reason: str | None = None,
    ) -> Ticket:
        ticket = await self._repository.get(tenant_id, ticket_id)
        if ticket is None:
            raise ValueError("Ticket not found")
        if action not in {"accept", "edit", "reject"}:
            raise ValueError("Unsupported review action")
        if ticket.status == TicketStatus.READY_TO_PUBLISH and action in {"accept", "edit"}:
            return ticket
        if ticket.status == TicketStatus.ESCALATED and action == "reject":
            return ticket
        if ticket.status != TicketStatus.WAITING_REVIEW:
            raise ValueError("Ticket is not waiting for review")

        draft = ticket.metadata.get("draft")
        draft_payload = draft if isinstance(draft, dict) else {}
        original_draft_text = str(draft_payload.get("reply_text", ""))
        review = {"action": action, "reviewer_id": reviewer_id}
        if action == "edit":
            if not isinstance(edited_text, str) or not edited_text.strip():
                raise ValueError("edited_text is required for edit")
            if not isinstance(draft, dict):
                raise ValueError("Ticket has no draft to edit")
            draft["reply_text"] = edited_text.strip()
            review["edited_text"] = edited_text.strip()
            ticket.transition_to(TicketStatus.READY_TO_PUBLISH)
            event_type = "ticket.review.edited"
        elif action == "accept":
            ticket.transition_to(TicketStatus.READY_TO_PUBLISH)
            event_type = "ticket.review.accepted"
        else:
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("reason is required for reject")
            review["reason"] = reason.strip()
            ticket.transition_to(TicketStatus.ESCALATED)
            event_type = "ticket.review.rejected"

        ticket.metadata["review"] = review
        trace_id = str(uuid4())
        await self._repository.save(
            ticket,
            events=[self._make_event(event_type, ticket, trace_id)],
        )
        await self._record_audit(
            action=event_type,
            ticket=ticket,
            actor_type="user",
            actor_id=reviewer_id,
            trace_id=trace_id,
            payload=review,
        )
        final_draft = ticket.metadata.get("draft")
        final_text = (
            str(final_draft.get("reply_text", ""))
            if isinstance(final_draft, dict)
            else original_draft_text
        )
        await self._record_evaluation_sample(
            ticket=ticket,
            action=action,
            reviewer_id=reviewer_id,
            original_draft_text=original_draft_text,
            final_text=final_text,
            reason=str(review.get("reason", "")),
            trace_id=trace_id,
            model_name=str(draft_payload.get("model_name", "")),
            provider=str(draft_payload.get("provider", "")),
        )
        return ticket

    async def publish_reply(
        self,
        tenant_id: str,
        ticket_id: str,
        text: str | None = None,
    ) -> Ticket:
        ticket = await self._repository.get(tenant_id, ticket_id)
        if ticket is None:
            raise ValueError("Ticket not found")
        if ticket.status == TicketStatus.PUBLISHED:
            return ticket
        if ticket.status != TicketStatus.READY_TO_PUBLISH:
            raise ValueError("Ticket is not ready to publish")
        if self._reply_connector is None:
            raise ValueError("Reply connector is not configured")

        if text is None:
            draft = ticket.metadata.get("draft")
            text = draft.get("reply_text") if isinstance(draft, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Reply text is required")
        text = text.strip()

        target = str(ticket.metadata.get("reply_target") or ticket.conversation_id or "")
        if not target:
            raise ValueError("Reply target is missing")
        response = await self._reply_connector.send_text(
            target=target,
            text=text,
            idempotency_key=f"reply-{ticket.ticket_id}",
        )
        ticket.metadata["reply"] = {
            "message_id": response.get("message_id", ""),
            "text": text,
        }
        ticket.transition_to(TicketStatus.PUBLISHED)
        trace_id = str(uuid4())
        await self._repository.save(
            ticket,
            events=[self._make_event("reply.published", ticket, trace_id)],
        )
        await self._record_audit(
            action="reply.published",
            ticket=ticket,
            actor_type="system",
            actor_id="support-ticket-service",
            trace_id=trace_id,
            payload={"message_id": ticket.metadata["reply"]["message_id"]},
        )
        return ticket

    @staticmethod
    def _make_event(event_type: str, ticket: Ticket, trace_id: str | None = None) -> EventEnvelope:
        return EventEnvelope(
            event_id=str(uuid4()),
            event_type=event_type,
            tenant_id=ticket.tenant_id,
            task_id=ticket.ticket_id,
            trace_id=trace_id or str(uuid4()),
            producer="support-ticket-service",
            payload={"ticket_id": ticket.ticket_id, "status": ticket.status.value},
        )

    async def _record_audit(
        self,
        action: str,
        ticket: Ticket,
        actor_type: str,
        actor_id: str,
        trace_id: str,
        payload: dict[str, Any],
    ) -> None:
        if self._audit_repository is None:
            return
        await self._audit_repository.save(
            AuditEvent(
                event_id=str(uuid4()),
                tenant_id=ticket.tenant_id,
                action=action,
                resource_type="ticket",
                resource_id=ticket.ticket_id,
                risk_level=ticket.risk_level,
                actor_type=actor_type,
                actor_id=actor_id,
                trace_id=trace_id,
                payload=payload,
            )
        )

    async def _record_evaluation_sample(
        self,
        ticket: Ticket,
        action: str,
        reviewer_id: str,
        original_draft_text: str,
        final_text: str,
        reason: str,
        trace_id: str,
        model_name: str,
        provider: str,
    ) -> None:
        if self._evaluation_repository is None:
            return
        await self._evaluation_repository.save(
            EvaluationSample(
                sample_id=str(uuid4()),
                tenant_id=ticket.tenant_id,
                source_ticket_id=ticket.ticket_id,
                query=str(ticket.metadata.get("raw_message") or ticket.subject),
                draft_text=original_draft_text,
                final_text=final_text,
                action=action,
                reason=reason,
                reviewer_id=reviewer_id,
                intent=ticket.intent,
                priority=ticket.priority,
                risk_level=ticket.risk_level,
                model_name=model_name,
                provider=provider,
                trace_id=trace_id,
            )
        )

    @staticmethod
    def _require(event: dict[str, Any], key: str) -> str:
        value = event.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing required event field: {key}")
        return value.strip()
