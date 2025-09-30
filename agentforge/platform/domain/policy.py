from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ValidationOutcome(str, Enum):
    """Verdict for an action against a tenant's policy."""

    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_APPROVAL = "requires_approval"


class PolicyDecision(BaseModel):
    """Result of evaluating an action request against RBAC + policy rules."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    principal: str
    action: str
    resource_type: str = ""
    resource_id: str = ""
    outcome: ValidationOutcome
    risk_level: str = "low"
    reasons: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def allowed(self) -> bool:
        return self.outcome == ValidationOutcome.ALLOWED


class ActionPolicy(BaseModel):
    """Declarative policy for a concrete action under the Policy Engine.

    Mirrors engineering spec 5.7: the Policy Engine owns action risk level,
    approval requirements, and execution allow-lists. ``allowed_roles`` is an
    allow-list of roles permitted to run the action; ``require_approval`` marks
    high-risk / write actions that must pass the approval loop before running.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    tenant_id: str
    action: str
    risk_level: str = "medium"
    allowed_roles: list[str] = Field(default_factory=list)
    required_permission: str | None = None
    require_approval: bool = False
    enabled: bool = True


class RelationTuple(BaseModel):
    """OpenFGA-style relation tuple (object#relation@subject).

    Kept intentionally simple so a real OpenFGA server can be swapped in later.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    object_type: str
    object_id: str
    relation: str
    subject_type: str
    subject_id: str
