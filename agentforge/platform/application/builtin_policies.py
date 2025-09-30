from __future__ import annotations

from agentforge.platform.domain.policy import ActionPolicy
from agentforge.platform.domain.rbac import Permission, Role


def builtin_policies() -> list[ActionPolicy]:
    """Declarative default action policies.

    Fail-closed: only actions listed here are promotable. ``ticket.writeback``
    is a high-risk write action that always requires approval.
    """
    return [
        ActionPolicy(
            name="ticket_writeback",
            tenant_id="*",
            action="ticket.writeback",
            risk_level="high",
            required_permission="ticket.writeback",
            require_approval=True,
            allowed_roles=[],
            enabled=True,
        ),
        ActionPolicy(
            name="ticket_view",
            tenant_id="*",
            action="ticket.view",
            risk_level="low",
            required_permission="ticket.read",
            require_approval=False,
            allowed_roles=[],
            enabled=True,
        ),
    ]


def _async_relation_check(openfga_client):
    """Return an async callable wrapper around the OpenFGA client check."""

    async def _check(tuple_) -> bool:
        return openfga_client.acheck(
            tuple_.tenant_id,
            tuple_.object_type,
            tuple_.object_id,
            tuple_.relation,
            tuple_.subject_id,
        )

    return _check


async def seed_rbac(repository) -> None:
    """Idempotently seed built-in roles iff no roles exist yet."""
    roles = [
        Role(
            role_id="role-support-admin",
            tenant_id="*",
            name="support_admin",
            description="Tenant admin with full ticket and write-back rights.",
            permissions=[
                Permission.TICKET_READ,
                Permission.TICKET_WRITEBACK,
                Permission.TICKET_APPROVE,
                Permission.CONNECTOR_MANAGE,
            ],
            built_in=True,
        ),
        Role(
            role_id="role-support-agent",
            tenant_id="*",
            name="support_agent",
            description="Support agent who can view and draft replies.",
            permissions=[Permission.TICKET_READ, Permission.TICKET_REPLY],
            built_in=True,
        ),
    ]
    existing = await repository.list_roles("*")
    if existing:
        return
    for role in roles:
        await repository.save_role(role)
