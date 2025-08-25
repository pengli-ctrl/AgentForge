from __future__ import annotations

from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from agentforge.platform.application.knowledge_embedder import EMBEDDING_DIM
from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.evaluation import EvaluationSample
from agentforge.platform.domain.regression import (
    GoldenItem,
    RegressionRun,
    RegressionRunStatus,
)
from agentforge.platform.domain.ticket import RiskLevel, Ticket, TicketPriority, TicketStatus
from agentforge.platform.infrastructure.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TicketRecord(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_tickets_tenant_idempotency"),
    )

    ticket_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(Text(), default="")
    status: Mapped[str] = mapped_column(String(32), index=True)
    priority: Mapped[str] = mapped_column(String(8))
    intent: Mapped[str | None] = mapped_column(String(128), nullable=True)
    product: Mapped[str | None] = mapped_column(String(128), nullable=True)
    assigned_team: Mapped[str | None] = mapped_column(String(128), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    version: Mapped[int] = mapped_column(default=1)

    @classmethod
    def from_domain(cls, ticket: Ticket) -> "TicketRecord":
        return cls(
            ticket_id=ticket.ticket_id,
            tenant_id=ticket.tenant_id,
            customer_id=ticket.customer_id,
            conversation_id=ticket.conversation_id,
            source=ticket.source,
            subject=ticket.subject,
            status=ticket.status.value,
            priority=ticket.priority.value,
            intent=ticket.intent,
            product=ticket.product,
            assigned_team=ticket.assigned_team,
            risk_level=ticket.risk_level.value,
            confidence=ticket.confidence,
            idempotency_key=ticket.idempotency_key,
            payload=ticket.metadata,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            version=ticket.version,
        )

    def apply_domain(self, ticket: Ticket) -> None:
        self.customer_id = ticket.customer_id
        self.conversation_id = ticket.conversation_id
        self.subject = ticket.subject
        self.status = ticket.status.value
        self.priority = ticket.priority.value
        self.intent = ticket.intent
        self.product = ticket.product
        self.assigned_team = ticket.assigned_team
        self.risk_level = ticket.risk_level.value
        self.confidence = ticket.confidence
        self.idempotency_key = ticket.idempotency_key
        self.payload = ticket.metadata
        self.updated_at = ticket.updated_at
        self.version = ticket.version

    def to_domain(self) -> Ticket:
        return Ticket(
            ticket_id=self.ticket_id,
            tenant_id=self.tenant_id,
            customer_id=self.customer_id,
            conversation_id=self.conversation_id,
            source=self.source,
            subject=self.subject,
            status=TicketStatus(self.status),
            priority=TicketPriority(self.priority),
            intent=self.intent,
            product=self.product,
            assigned_team=self.assigned_team,
            risk_level=RiskLevel(self.risk_level),
            confidence=self.confidence,
            idempotency_key=self.idempotency_key,
            metadata=self.payload or {},
            created_at=self.created_at,
            updated_at=self.updated_at,
            version=self.version,
        )


class OutboxEventRecord(Base):
    __tablename__ = "outbox_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text(), nullable=True)

    @classmethod
    def from_event(cls, event) -> "OutboxEventRecord":
        return cls(
            event_id=event.event_id,
            tenant_id=event.tenant_id,
            event_type=event.event_type,
            payload=event.model_dump(mode="json"),
            status="pending",
            created_at=event.occurred_at,
        )


class KnowledgeDocumentRecord(Base):
    __tablename__ = "knowledge_documents"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text())
    source_uri: Mapped[str] = mapped_column(String(512), default="")
    version: Mapped[int] = mapped_column(default=1)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class KnowledgeChunkRecord(Base):
    __tablename__ = "knowledge_chunks"

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[str] = mapped_column(Text())
    position: Mapped[int] = mapped_column()
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_version: Mapped[int | None] = mapped_column(nullable=True)


class CostRecordRecord(Base):
    __tablename__ = "cost_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    model_name: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    amount: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    resource_type: Mapped[str] = mapped_column(String(64), index=True)
    resource_id: Mapped[str] = mapped_column(String(64), index=True)
    risk_level: Mapped[str] = mapped_column(String(32))
    actor_type: Mapped[str] = mapped_column(String(32), default="system")
    actor_id: Mapped[str] = mapped_column(String(128), default="agentforge")
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(cls, event: AuditEvent) -> "AuditEventRecord":
        return cls(
            event_id=event.event_id,
            tenant_id=event.tenant_id,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            risk_level=event.risk_level.value,
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            trace_id=event.trace_id,
            payload=event.payload,
            created_at=event.occurred_at,
        )

    def to_domain(self) -> AuditEvent:
        return AuditEvent(
            event_id=self.event_id,
            tenant_id=self.tenant_id,
            action=self.action,
            resource_type=self.resource_type,
            resource_id=self.resource_id,
            risk_level=RiskLevel(self.risk_level),
            actor_type=self.actor_type,
            actor_id=self.actor_id,
            trace_id=self.trace_id,
            payload=self.payload or {},
            occurred_at=self.created_at,
        )


class EvaluationSampleRecord(Base):
    __tablename__ = "evaluation_samples"

    sample_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    source_ticket_id: Mapped[str] = mapped_column(String(64), index=True)
    query: Mapped[str] = mapped_column(Text())
    draft_text: Mapped[str] = mapped_column(Text())
    final_text: Mapped[str] = mapped_column(Text())
    action: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str] = mapped_column(Text(), default="")
    reviewer_id: Mapped[str] = mapped_column(String(128))
    intent: Mapped[str | None] = mapped_column(String(128), nullable=True)
    priority: Mapped[str] = mapped_column(String(8))
    risk_level: Mapped[str] = mapped_column(String(32))
    model_name: Mapped[str] = mapped_column(String(128), default="")
    provider: Mapped[str] = mapped_column(String(64), default="")
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(cls, sample: EvaluationSample) -> "EvaluationSampleRecord":
        return cls(
            sample_id=sample.sample_id,
            tenant_id=sample.tenant_id,
            source_ticket_id=sample.source_ticket_id,
            query=sample.query,
            draft_text=sample.draft_text,
            final_text=sample.final_text,
            action=sample.action,
            reason=sample.reason,
            reviewer_id=sample.reviewer_id,
            intent=sample.intent,
            priority=sample.priority.value,
            risk_level=sample.risk_level.value,
            model_name=sample.model_name,
            provider=sample.provider,
            trace_id=sample.trace_id,
            created_at=sample.created_at,
        )

    def to_domain(self) -> EvaluationSample:
        return EvaluationSample(
            sample_id=self.sample_id,
            tenant_id=self.tenant_id,
            source_ticket_id=self.source_ticket_id,
            query=self.query,
            draft_text=self.draft_text,
            final_text=self.final_text,
            action=self.action,
            reason=self.reason,
            reviewer_id=self.reviewer_id,
            intent=self.intent,
            priority=TicketPriority(self.priority),
            risk_level=RiskLevel(self.risk_level),
            model_name=self.model_name,
            provider=self.provider,
            trace_id=self.trace_id,
            created_at=self.created_at,
        )


class GoldenItemRecord(Base):
    __tablename__ = "golden_items"

    item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    query: Mapped[str] = mapped_column(Text())
    expected_chunk_ids: Mapped[list] = mapped_column(JSON(), default=list)
    expected_citations: Mapped[list] = mapped_column(JSON(), default=list)
    expected_intent: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expected_priority: Mapped[str | None] = mapped_column(String(8), nullable=True)
    expected_risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(cls, item: GoldenItem) -> "GoldenItemRecord":
        return cls(
            item_id=item.item_id,
            tenant_id=item.tenant_id,
            query=item.query,
            expected_chunk_ids=item.expected_chunk_ids,
            expected_citations=item.expected_citations,
            expected_intent=item.expected_intent,
            expected_priority=item.expected_priority,
            expected_risk_level=item.expected_risk_level,
            created_at=item.created_at,
        )

    def to_domain(self) -> GoldenItem:
        return GoldenItem(
            item_id=self.item_id,
            tenant_id=self.tenant_id,
            query=self.query,
            expected_chunk_ids=list(self.expected_chunk_ids or []),
            expected_citations=list(self.expected_citations or []),
            expected_intent=self.expected_intent,
            expected_priority=self.expected_priority,
            expected_risk_level=self.expected_risk_level,
            created_at=self.created_at,
        )


class RegressionRunRecord(Base):
    __tablename__ = "regression_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    candidate_id: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16))
    recall_at_k: Mapped[float] = mapped_column(default=0.0)
    citation_accuracy: Mapped[float] = mapped_column(default=0.0)
    classification_accuracy: Mapped[float] = mapped_column(default=0.0)
    priority_accuracy: Mapped[float] = mapped_column(default=0.0)
    structured_output_rate: Mapped[float] = mapped_column(default=0.0)
    high_risk_miss_rate: Mapped[float] = mapped_column(default=0.0)
    verdict: Mapped[str] = mapped_column(String(16), default="block")
    report: Mapped[dict] = mapped_column(JSON(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(
        cls, run: RegressionRun, report_dict: dict | None = None
    ) -> "RegressionRunRecord":
        return cls(
            run_id=run.run_id,
            tenant_id=run.tenant_id,
            candidate_id=run.candidate_id,
            status=run.status.value,
            recall_at_k=run.recall_at_k,
            citation_accuracy=run.citation_accuracy,
            classification_accuracy=run.classification_accuracy,
            priority_accuracy=run.priority_accuracy,
            structured_output_rate=run.structured_output_rate,
            high_risk_miss_rate=run.high_risk_miss_rate,
            verdict=run.verdict,
            report=report_dict or {},
            created_at=run.created_at,
        )

    def to_domain(self) -> RegressionRun:
        return RegressionRun(
            run_id=self.run_id,
            tenant_id=self.tenant_id,
            candidate_id=self.candidate_id,
            status=RegressionRunStatus(self.status),
            recall_at_k=self.recall_at_k,
            citation_accuracy=self.citation_accuracy,
            classification_accuracy=self.classification_accuracy,
            priority_accuracy=self.priority_accuracy,
            structured_output_rate=self.structured_output_rate,
            high_risk_miss_rate=self.high_risk_miss_rate,
            verdict=self.verdict,
            created_at=self.created_at,
        )
