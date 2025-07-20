from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TicketStatus(str, Enum):
    NEW = "new"
    CLASSIFYING = "classifying"
    WAITING_REVIEW = "waiting_review"
    WAITING_APPROVAL = "waiting_approval"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHED = "published"
    ESCALATED = "escalated"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TicketPriority(str, Enum):
    P0 = "p0"
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"


class RiskLevel(str, Enum):
    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


ALLOWED_TRANSITIONS = {
    TicketStatus.NEW: {TicketStatus.CLASSIFYING, TicketStatus.CANCELLED},
    TicketStatus.CLASSIFYING: {
        TicketStatus.WAITING_REVIEW,
        TicketStatus.WAITING_APPROVAL,
        TicketStatus.ESCALATED,
        TicketStatus.FAILED,
    },
    TicketStatus.WAITING_REVIEW: {
        TicketStatus.READY_TO_PUBLISH,
        TicketStatus.WAITING_APPROVAL,
        TicketStatus.ESCALATED,
        TicketStatus.CANCELLED,
    },
    TicketStatus.WAITING_APPROVAL: {
        TicketStatus.READY_TO_PUBLISH,
        TicketStatus.ESCALATED,
        TicketStatus.FAILED,
        TicketStatus.CANCELLED,
    },
    TicketStatus.READY_TO_PUBLISH: {TicketStatus.PUBLISHED, TicketStatus.FAILED},
    TicketStatus.ESCALATED: {TicketStatus.READY_TO_PUBLISH, TicketStatus.CANCELLED},
    TicketStatus.FAILED: {TicketStatus.CLASSIFYING, TicketStatus.CANCELLED},
    TicketStatus.PUBLISHED: set(),
    TicketStatus.CANCELLED: set(),
}


class Ticket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    tenant_id: str
    customer_id: str | None = None
    conversation_id: str | None = None
    source: str
    subject: str = ""
    status: TicketStatus = TicketStatus.NEW
    priority: TicketPriority = TicketPriority.P3
    intent: str | None = None
    product: str | None = None
    assigned_team: str | None = None
    risk_level: RiskLevel = RiskLevel.READ_ONLY
    confidence: float | None = None
    idempotency_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1

    def can_transition_to(self, new_status: TicketStatus) -> bool:
        return new_status in ALLOWED_TRANSITIONS[self.status]

    def transition_to(self, new_status: TicketStatus) -> None:
        if not self.can_transition_to(new_status):
            raise ValueError("Invalid ticket transition")
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
