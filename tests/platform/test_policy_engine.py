from __future__ import annotations

from agentforge.platform.application.builtin_policies import builtin_policies
from agentforge.platform.application.openfga_adapter import OpenFGAClient
from agentforge.platform.application.policy_engine import PolicyEngine
from agentforge.platform.domain.policy import (
    ActionPolicy,
    RelationTuple,
    ValidationOutcome,
)


async def test_unknown_action_fails_closed() -> None:
    engine = PolicyEngine(policies=builtin_policies())
    decision = await engine.authorize(
        tenant_id="t1",
        principal="user-1",
        action="ticket.delete",
        roles=["admin"],
    )
    assert decision.allowed is False
    assert decision.outcome == ValidationOutcome.DENIED


async def test_writeback_requires_approval_even_for_admin() -> None:
    engine = PolicyEngine(policies=builtin_policies())
    decision = await engine.authorize(
        tenant_id="t1",
        principal="user-1",
        action="ticket.writeback",
        roles=["admin"],
    )
    assert decision.outcome == ValidationOutcome.REQUIRES_APPROVAL
    assert decision.allowed is False


async def test_view_allowed_with_permission_and_role() -> None:
    engine = PolicyEngine(policies=builtin_policies())
    decision = await engine.authorize(
        tenant_id="t1",
        principal="user-1",
        action="ticket.view",
        roles=["support_admin"],
        permissions=["ticket.read"],
    )
    assert decision.outcome == ValidationOutcome.ALLOWED
    assert decision.allowed is True


async def test_writeback_without_view_permission_denied() -> None:
    engine = PolicyEngine(policies=builtin_policies())
    decision = await engine.authorize(
        tenant_id="t1",
        principal="user-1",
        action="ticket.view",
        roles=["support_admin"],
        permissions=["ticket.reply"],
    )
    assert decision.outcome == ValidationOutcome.DENIED


async def test_disabled_policy_denied() -> None:
    engine = PolicyEngine(
        policies=[
            ActionPolicy(
                name="p",
                tenant_id="t1",
                action="a",
                enabled=False,
                required_permission="ticket.read",
            )
        ]
    )
    decision = await engine.authorize(
        tenant_id="t1",
        principal="u",
        action="a",
        roles=["admin"],
    )
    assert decision.outcome == ValidationOutcome.DENIED
    assert "disabled" in decision.reasons[0]


async def test_relation_check_gates_resource_access() -> None:
    client = OpenFGAClient()
    client.write(
        "t1",
        [
            RelationTuple(
                tenant_id="t1",
                object_type="ticket",
                object_id="tk-1",
                relation="viewer",
                subject_type="user",
                subject_id="user-1",
            )
        ],
    )
    engine = PolicyEngine(
        policies=builtin_policies(),
        relation_check=lambda t: client.acheck(
            t.tenant_id, t.object_type, t.object_id, t.relation, t.subject_id
        ),
    )
    decision = await engine.authorize(
        tenant_id="t1",
        principal="user-1",
        action="ticket.view",
        roles=["support_admin"],
        permissions=["ticket.read"],
        resource_type="ticket",
        resource_id="tk-1",
        relation="viewer",
    )
    assert decision.allowed is True

    denied = await engine.authorize(
        tenant_id="t1",
        principal="user-2",
        action="ticket.view",
        roles=["support_admin"],
        permissions=["ticket.read"],
        resource_type="ticket",
        resource_id="tk-1",
        relation="viewer",
    )
    assert denied.allowed is False
    assert "relation" in denied.reasons[0]


async def test_custom_tenant_policy() -> None:
    engine = PolicyEngine(
        policies=[
            ActionPolicy(
                name="custom",
                tenant_id="t9",
                action="ticket.view",
                allowed_roles=["support_admin"],
                enabled=True,
            )
        ]
    )
    ok = await engine.authorize(
        tenant_id="t9", principal="u", action="ticket.view", roles=["support_admin"]
    )
    assert ok.allowed is True
    bad = await engine.authorize(
        tenant_id="t9", principal="u", action="ticket.view", roles=["support_agent"]
    )
    assert bad.allowed is False
