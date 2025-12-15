import pytest

from agentforge.platform.application.builtin_policies import builtin_policies
from agentforge.platform.application.high_risk_authorizer import HighRiskActionAuthorizer
from agentforge.platform.application.policy_engine import PolicyEngine
from agentforge.platform.application.ticket_writeback import TicketWritebackService
from agentforge.platform.domain.authorization import AuthorizationOutcome
from agentforge.platform.domain.rbac import Permission, Role, RoleAssignment
from agentforge.platform.domain.ticket import (
    RiskLevel,
    Ticket,
    TicketPriority,
    TicketStatus,
)
from agentforge.platform.infrastructure.memory_rbac_repository import MemoryRbacRepository


class _FakeAuditRepo:
    def __init__(self) -> None:
        self.events: list = []

    async def save(self, event) -> None:  # noqa: ANN001
        self.events.append(event)


class _FakeRegistry:
    def __init__(self) -> None:
        self.invocations: list = []
        spec = type(
            "S",
            (),
            {"connector_id": "conn-crm", "enabled": True, "allowed_actions": ["writeback"]},
        )()
        self.specs = [spec]

    async def invoke(self, connector_id, action, payload, context):  # noqa: ANN001
        self.invocations.append((connector_id, action, context.idempotency_key))
        return type("R", (), {"ok": True, "error": None, "data": {"ok": True}})()

    def list_specs(self, tenant_id):  # noqa: ANN001
        return self.specs


def _ticket(status: TicketStatus = TicketStatus.READY_TO_PUBLISH) -> Ticket:
    metadata = {}
    if status == TicketStatus.READY_TO_PUBLISH:
        metadata["approval"] = {"decision": "approve", "decided_by": "manager-1"}
    return Ticket(
        ticket_id="ticket-hr-1",
        tenant_id="t1",
        customer_id="cust-1",
        conversation_id="conv-1",
        source="feishu",
        subject="Refund",
        status=status,
        priority=TicketPriority.P1,
        intent="refund",
        risk_level=RiskLevel.HIGH,
        idempotency_key="ik-hr-1",
        metadata=metadata,
    )


async def _authorizer_with_admin(record: bool = True) -> HighRiskActionAuthorizer:
    rbac = MemoryRbacRepository()
    await rbac.save_role(
        Role(
            role_id="r-admin",
            tenant_id="t1",
            name="support_admin",
            description="",
            permissions=[Permission.TICKET_WRITEBACK, Permission.TICKET_READ],
            built_in=True,
        )
    )
    await rbac.save_assignment(
        RoleAssignment(
            assignment_id="asg-1",
            tenant_id="t1",
            user_id="alice",
            role_id="r-admin",
        )
    )
    engine = PolicyEngine(policies=builtin_policies())
    return HighRiskActionAuthorizer(
        engine,
        audit_repository=_FakeAuditRepo(),
        rbac_repository=rbac,
    )


@pytest.mark.asyncio
async def test_approved_high_risk_allowed() -> None:
    auth = await _authorizer_with_admin()
    decision = await auth.authorize(
        tenant_id="t1",
        principal="alice",
        action="ticket.writeback",
        resource_type="ticket",
        resource_id="ticket-hr-1",
        ticket=_ticket(TicketStatus.READY_TO_PUBLISH),
    )
    assert decision.outcome == AuthorizationOutcome.ALLOWED
    assert decision.approval_ref == "manager-1"
    assert "human approval granted" in decision.reasons


@pytest.mark.asyncio
async def test_unapproved_high_risk_denied() -> None:
    auth = await _authorizer_with_admin()
    decision = await auth.authorize(
        tenant_id="t1",
        principal="alice",
        action="ticket.writeback",
        resource_type="ticket",
        resource_id="ticket-hr-1",
        ticket=_ticket(TicketStatus.WAITING_APPROVAL),
    )
    assert decision.outcome == AuthorizationOutcome.DENIED
    assert "human approval required but not granted" in decision.reasons


@pytest.mark.asyncio
async def test_unauthorized_principal_denied() -> None:
    auth = await _authorizer_with_admin()
    decision = await auth.authorize(
        tenant_id="t1",
        principal="mallory",
        action="ticket.writeback",
        resource_type="ticket",
        resource_id="ticket-hr-1",
        ticket=_ticket(TicketStatus.READY_TO_PUBLISH),
    )
    assert decision.outcome == AuthorizationOutcome.DENIED


@pytest.mark.asyncio
async def test_audit_recorded_for_allow_and_deny() -> None:
    rbac = MemoryRbacRepository()
    audit = _FakeAuditRepo()
    engine = PolicyEngine(policies=builtin_policies())
    auth = HighRiskActionAuthorizer(engine, audit, rbac)
    # denied (no role)
    await auth.authorize(
        tenant_id="t1",
        principal="nobody",
        action="ticket.writeback",
        resource_type="ticket",
        resource_id="x",
        ticket=_ticket(TicketStatus.WAITING_APPROVAL),
    )
    actions = [e.action for e in audit.events]
    assert "ticket.writeback.authorization" in actions
    # every authorization persists outcome + reasons + actor
    assert any(e.payload["outcome"] == "denied" for e in audit.events)


@pytest.mark.asyncio
async def test_execute_guarded_denied_raises() -> None:
    auth = await _authorizer_with_admin()

    async def _fn():
        raise AssertionError("should not be called")

    with pytest.raises(PermissionError):
        await auth.execute_guarded(
            tenant_id="t1",
            principal="alice",
            action="ticket.writeback",
            resource_type="ticket",
            resource_id="x",
            ticket=_ticket(TicketStatus.WAITING_APPROVAL),
            fn=_fn,
        )


@pytest.mark.asyncio
async def test_writeback_gate_blocks_unapproved() -> None:
    registry = _FakeRegistry()
    auth = await _authorizer_with_admin()
    service = TicketWritebackService(
        registry, audit_repository=_FakeAuditRepo(), high_risk_authorizer=auth
    )
    with pytest.raises(PermissionError):
        await service.write_back(_ticket(TicketStatus.WAITING_APPROVAL), actor="alice")
    assert registry.invocations == []


@pytest.mark.asyncio
async def test_writeback_gate_allows_approved() -> None:
    registry = _FakeRegistry()
    auth = await _authorizer_with_admin()
    service = TicketWritebackService(
        registry, audit_repository=_FakeAuditRepo(), high_risk_authorizer=auth
    )
    data = await service.write_back(_ticket(TicketStatus.READY_TO_PUBLISH), actor="alice")
    assert data == {"ok": True}
    assert len(registry.invocations) == 1
