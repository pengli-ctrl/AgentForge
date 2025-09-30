from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AuthorizationOutcome(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_APPROVAL = "requires_approval"


class AuthorizationDecision(BaseModel):
    """Audit-grade record of a high-risk action authorization check.

    Answers the "who executed / why allowed" acceptance question: for every
    high-risk action we persist the principal, the action, the policy reason
    chain, the approval reference (when applicable) and the final outcome. This
    is the durable loop that makes every high-risk action traceable.
    """

    model_config = ConfigDict(extra="forbid")

    authorization_id: str
    tenant_id: str
    action: str
    resource_type: str
    resource_id: str
    principal: str
    outcome: AuthorizationOutcome
    reasons: list[str] = Field(default_factory=list)
    approval_ref: str | None = None
    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
