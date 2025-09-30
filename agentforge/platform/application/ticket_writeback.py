from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from agentforge.platform.application.connector_registry import ConnectorRegistry
from agentforge.platform.application.ports import AuditRepository
from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.authorization import AuthorizationOutcome
from agentforge.platform.domain.connector import ConnectorContext
from agentforge.platform.domain.ticket import Ticket

Resolver = Callable[[str], str | None]


class TicketWritebackService:
    """Writes an approved/published ticket action back to an external system.

    Closes the "read -> AI -> approve -> write-back" loop (engineering spec
    stage-3 acceptance): given a published ticket, invoke a tenant's registered
    CRM / ticket-system connector via the ConnectorRegistry and persist the
    outcome as an audit event. Uses the ticket_id as the idempotency key, so a
    replay of the same write-back is deduplicated at the connected system.

    When a :class:`HighRiskActionAuthorizer` is supplied it acts as the
    human-authorization boundary: a high-risk write-back that has not been
    approved is rejected up front (PermissionError) instead of being executed,
    closing the "who executed / why allowed" audit loop.
    """

    def __init__(
        self,
        registry: ConnectorRegistry,
        audit_repository: AuditRepository | None = None,
        connector_resolver: Callable[[str], str | None] | None = None,
        high_risk_authorizer=None,
    ) -> None:
        self._registry = registry
        self._audit_repository = audit_repository
        # connector_resolver: (tenant_id) -> connector_id to use for write-back
        # defaults to the first enabled connector of that tenant.
        self._connector_resolver = connector_resolver
        self._high_risk_authorizer = high_risk_authorizer

    async def _check_authorization(self, ticket: Ticket, action: str, actor: str) -> None:
        if self._high_risk_authorizer is None:
            return
        decision = await self._high_risk_authorizer.authorize(
            tenant_id=ticket.tenant_id,
            principal=actor,
            action=action,
            resource_type="ticket",
            resource_id=ticket.ticket_id,
            ticket=ticket,
        )
        if decision.outcome != AuthorizationOutcome.ALLOWED:
            raise PermissionError("; ".join(decision.reasons))

    async def write_back(
        self,
        ticket: Ticket,
        action: str = "ticket.writeback",
        *,
        actor: str = "support-writeback",
    ) -> dict[str, Any]:
        await self._check_authorization(ticket, action, actor)
        connector_id = self._resolve_connector(ticket.tenant_id)
        if connector_id is None:
            raise ValueError("No write-back connector registered for tenant")

        payload = self._build_payload(ticket)
        context = ConnectorContext(
            tenant_id=ticket.tenant_id,
            task_id=ticket.ticket_id,
            idempotency_key=f"wb-{ticket.ticket_id}",
            trace_id=str(uuid4()),
            actor=actor,
        )
        result = await self._registry.invoke(
            connector_id,
            action,
            payload,
            context,
        )
        await self._record_audit(ticket, action, result, context.trace_id)
        if not result.ok:
            raise RuntimeError(result.error or "write-back failed")
        return result.data

    def _resolve_connector(self, tenant_id: str) -> str | None:
        if self._connector_resolver is not None:
            return self._connector_resolver(tenant_id)
        specs = self._registry.list_specs(tenant_id)
        for spec in specs:
            if spec.enabled and ("writeback" in spec.allowed_actions or not spec.allowed_actions):
                return spec.connector_id
        return None

    @staticmethod
    def _build_payload(ticket: Ticket) -> dict[str, Any]:
        reply = ticket.metadata.get("reply") or {}
        draft = ticket.metadata.get("draft") or {}
        draft_text = draft.get("reply_text") if isinstance(draft, dict) else None
        return {
            "method": "POST",
            "path": "/tickets",
            "body": {
                "ticket_id": ticket.ticket_id,
                "conversation_id": ticket.conversation_id,
                "customer_id": ticket.customer_id,
                "subject": ticket.subject,
                "reply_text": reply.get("text") if isinstance(reply, dict) else None,
                "draft_text": draft_text,
                "status": ticket.status.value,
                "priority": ticket.priority.value,
                "intent": ticket.intent,
            },
        }

    async def _record_audit(
        self,
        ticket: Ticket,
        action: str,
        result: Any,
        trace_id: str,
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
                actor_id="support-ticket-writeback",
                trace_id=trace_id,
                payload={
                    "ok": result.ok,
                    "error": result.error,
                    "idempotency_key": f"wb-{ticket.ticket_id}",
                },
            )
        )
