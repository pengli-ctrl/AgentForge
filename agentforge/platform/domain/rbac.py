from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Permission(str, Enum):
    """Granular permissions a role can grant (action-level RBAC).

    Actions are grouped per resource; the ``role`` name is a coarse tag used
    by policy while permissions drive the actual allow/deny decision.
    """

    # Ticket resource
    TICKET_READ = "ticket.read"
    TICKET_REVIEW = "ticket.review"
    TICKET_APPROVE = "ticket.approve"
    TICKET_REPLY = "ticket.reply"
    TICKET_WRITEBACK = "ticket.writeback"
    # Knowledge resource
    KNOWLEDGE_READ = "knowledge.read"
    KNOWLEDGE_WRITE = "knowledge.write"
    # Connector / integration
    CONNECTOR_READ = "connector.read"
    CONNECTOR_MANAGE = "connector.manage"
    # Audit & operations
    AUDIT_READ = "audit.read"
    # Admin
    ADMIN = "admin.*"


_ROLE_PERMISSIONS: dict[str, set[Permission]] = {
    "admin": {
        Permission.ADMIN,
        Permission.TICKET_READ,
        Permission.TICKET_REVIEW,
        Permission.TICKET_APPROVE,
        Permission.TICKET_REPLY,
        Permission.TICKET_WRITEBACK,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.CONNECTOR_READ,
        Permission.CONNECTOR_MANAGE,
        Permission.AUDIT_READ,
    },
    "agent": {
        Permission.TICKET_READ,
        Permission.TICKET_REVIEW,
        Permission.TICKET_REPLY,
        Permission.KNOWLEDGE_READ,
        Permission.CONNECTOR_READ,
    },
    "supervisor": {
        Permission.TICKET_READ,
        Permission.TICKET_APPROVE,
        Permission.AUDIT_READ,
        Permission.KNOWLEDGE_READ,
    },
    "auditor": {
        Permission.AUDIT_READ,
        Permission.TICKET_READ,
        Permission.CONNECTOR_READ,
    },
}


def role_permissions(role: str) -> set[Permission]:
    """Return the built-in permission set for a built-in role."""
    return set(_ROLE_PERMISSIONS.get(role, set()))


class Role(BaseModel):
    """A role holder with a name and explicit permission grant."""

    model_config = ConfigDict(extra="forbid")

    role_id: str
    tenant_id: str
    name: str
    description: str = ""
    permissions: list[Permission] = Field(default_factory=list)
    built_in: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoleAssignment(BaseModel):
    """A user is granted a role within a tenant."""

    model_config = ConfigDict(extra="forbid")

    assignment_id: str
    tenant_id: str
    user_id: str
    role_id: str
    granted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
