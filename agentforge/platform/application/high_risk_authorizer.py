from __future__ import annotations

from typing import Any
from uuid import uuid4

from agentforge.platform.application.policy_engine import PolicyEngine
from agentforge.platform.application.ports import AuditRepository
from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.authorization import (
    AuthorizationDecision,
    AuthorizationOutcome,
)
from agentforge.platform.domain.ticket import RiskLevel, Ticket, TicketStatus
from agentforge.platform.infrastructure.memory_rbac_repository import MemoryRbacRepository


class HighRiskActionAuthorizer:
    """An authorization gate for high-risk (typically write) actions.

    Closes the "who executed / why allowed" audit loop (engineering spec stage-3
    acceptance): resolves the caller's roles/permissions, evaluates the action
    against the PolicyEngine, enforces the human-approval boundary (a high-risk
    action that requires approval may only run after the ticket has been
    approved), and records BOTH the allowance and every denial as durable audit
    events. Fails closed: unknown/disabled policies and missing approval yield a
    denial, never a silent allow.
    """

    def __init__(
        self,
        policy_engine: PolicyEngine,
        audit_repository: AuditRepository | None = None,
        rbac_repository=None,
    ) -> None:
        self._policy_engine = policy_engine
        self._audit_repository = audit_repository
        if rbac_repository is None:
            rbac_repository = MemoryRbacRepository()
        self._rbac_repository = rbac_repository

    async def authorize(
        self,
        *,
        tenant_id: str,
        principal: str,
        action: str,
        resource_type: str,
        resource_id: str,
        ticket: Ticket | None = None,
        relation: str | None = None,
        record: bool = True,
    ) -> AuthorizationDecision:
        roles, permissions = await self._resolve_identity(tenant_id, principal)

        policy_decision = await self._policy_engine.authorize(
            tenant_id=tenant_id,
            principal=principal,
            action=action,
            roles=roles,
            permissions=permissions,
            resource_type=resource_type,
            resource_id=resource_id,
            relation=relation,
        )

        outcome_map = {
            "allowed": AuthorizationOutcome.ALLOWED,
            "denied": AuthorizationOutcome.DENIED,
            "requires_approval": AuthorizationOutcome.REQUIRES_APPROVAL,
        }
        outcome = outcome_map.get(policy_decision.outcome.value, AuthorizationOutcome.DENIED)

        approval_ref = None
        reasons = list(policy_decision.reasons)
        # Human-approval boundary: a high-risk action that requires approval may
        # only run after the ticket has been approved (READY_TO_PUBLISH).
        if outcome == AuthorizationOutcome.REQUIRES_APPROVAL:
            granted = self._approval_granted(ticket)
            if granted:
                outcome = AuthorizationOutcome.ALLOWED
                approval_ref = granted
                reasons.append("human approval granted")
            else:
                outcome = AuthorizationOutcome.DENIED
                reasons.append("human approval required but not granted")

        decision = AuthorizationDecision(
            authorization_id=f"authz-{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            principal=principal,
            outcome=outcome,
            reasons=reasons,
            approval_ref=approval_ref,
        )

        if record:
            await self._record_audit(tenant_id, decision, ticket)
        return decision

    @staticmethod
    def _approval_granted(ticket: Ticket | None) -> str | None:
        """Return an approval reference if the ticket has been human-approved."""
        if ticket is None:
            return None
        if ticket.status != TicketStatus.READY_TO_PUBLISH:
            return None
        approval = ticket.metadata.get("approval") or {}
        if approval.get("decision") != "approve":
            return None
        return approval.get("decided_by") or ticket.ticket_id

    async def _resolve_identity(self, tenant_id: str, principal: str) -> tuple[list[str], list]:
        roles: list[str] = []
        permissions: set = set()
        assignments = await self._rbac_repository.assignments_for_user(tenant_id, principal)
        for assignment in assignments:
            role = await self._rbac_repository.get_role(tenant_id, assignment.role_id)
            if role is not None:
                roles.append(role.name or assignment.role_id)
                permissions |= set(role.permissions)
        return roles, list(permissions)

    async def _record_audit(
        self,
        tenant_id: str,
        decision: AuthorizationDecision,
        ticket: Ticket | None,
    ) -> None:
        if self._audit_repository is None:
            return
        risk = (
            ticket.risk_level
            if ticket is not None and ticket.risk_level is not None
            else RiskLevel.HIGH
        )
        await self._audit_repository.save(
            AuditEvent(
                event_id=str(uuid4()),
                tenant_id=tenant_id,
                action=f"{decision.action}.authorization",
                resource_type=decision.resource_type,
                resource_id=decision.resource_id,
                risk_level=RiskLevel.HIGH,
                actor_type="user",
                actor_id=decision.principal,
                payload={
                    "outcome": decision.outcome.value,
                    "reasons": decision.reasons,
                    "approval_ref": decision.approval_ref,
                    "risk_level": risk.value,
                    "authorization_id": decision.authorization_id,
                },
            )
        )

    async def execute_guarded(
        self,
        *,
        tenant_id: str,
        principal: str,
        action: str,
        resource_type: str,
        resource_id: str,
        ticket: Ticket | None,
        fn: Any,
        **kwargs: Any,
    ) -> Any:
        """Human-authorization boundary wrapper around a high-risk callable.

        The callable is only invoked when authorization is granted; otherwise
        raises PermissionError with the reasons.
        """
        decision = await self.authorize(
            tenant_id=tenant_id,
            principal=principal,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ticket=ticket,
        )
        if decision.outcome != AuthorizationOutcome.ALLOWED:
            raise PermissionError("; ".join(decision.reasons))
        return await fn(**kwargs)
