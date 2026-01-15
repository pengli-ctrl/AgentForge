"""AgentForge 平台基础设施层：models。

本模块负责 models 相关的平台能力，是 平台基础设施层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要类：TicketRecord、OutboxEventRecord、KnowledgeDocumentRecord、KnowledgeChunkRecord、CostRecordRecord、AuditEventRecord、EvaluationSampleRecord、GoldenItemRecord。
- 主要函数：utc_now。
"""

from __future__ import annotations

from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from agentforge.platform.application.knowledge_embedder import EMBEDDING_DIM
from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.connector import (
    ConnectorKind,
    ConnectorRiskLevel,
    ConnectorSpec,
    CredentialReference,
)
from agentforge.platform.domain.evaluation import EvaluationSample
from agentforge.platform.domain.rbac import Permission, Role, RoleAssignment
from agentforge.platform.domain.regression import (
    GoldenItem,
    RegressionRun,
    RegressionRunStatus,
)
from agentforge.platform.domain.reporting import (
    ReportFormat,
    ReportRun,
    ReportType,
    ScheduledReport,
)
from agentforge.platform.domain.tenant_quota import TenantQuota
from agentforge.platform.domain.ticket import RiskLevel, Ticket, TicketPriority, TicketStatus
from agentforge.platform.infrastructure.db.base import Base


def utc_now() -> datetime:
    """执行 utc_now 对应的逻辑，并返回处理结果。

    Returns:
        datetime，函数执行后的结果。
    """
    return datetime.now(timezone.utc)


class TicketRecord(Base):
    """TicketRecord。

    TicketRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - __tablename__: 'tickets'。
    - __table_args__: 唯一约束，保证同一租户下幂等键唯一。
      对应约束名为 uq_tickets_tenant_idempotency。
    - ticket_id: Mapped[str]。
    - tenant_id: Mapped[str]。
    - customer_id: Mapped[str | None]。
    - conversation_id: Mapped[str | None]。
    - source: Mapped[str]。
    - subject: Mapped[str]。
    - status: Mapped[str]。
    - priority: Mapped[str]。
    - intent: Mapped[str | None]。
    - product: Mapped[str | None]。
    - assigned_team: Mapped[str | None]。
    - risk_level: Mapped[str]。
    - confidence: Mapped[float | None]。
    - idempotency_key: Mapped[str]。
    - payload: Mapped[dict]。
    - created_at: Mapped[datetime]。
    - updated_at: Mapped[datetime]。
    - version: Mapped[int]。
    - 方法 from_domain()。
    - 方法 apply_domain()。
    - 方法 to_domain()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

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
        """执行 from_domain 对应的逻辑，并返回处理结果。

        Args:
            ticket: Ticket，调用方传入的 ticket 参数。

        Returns:
            'TicketRecord'，函数执行后的结果。
        """
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
        """应用业务变更，并返回调用方需要的结果。

        Args:
            ticket: Ticket，调用方传入的 ticket 参数。

        Returns:
            None，函数执行后的结果。
        """
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
        """执行 to_domain 对应的逻辑，并返回处理结果。

        Returns:
            Ticket，函数执行后的结果。
        """
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
    """OutboxEventRecord。

    OutboxEventRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - __tablename__: 'outbox_events'。
    - event_id: Mapped[str]。
    - tenant_id: Mapped[str]。
    - event_type: Mapped[str]。
    - payload: Mapped[dict]。
    - status: Mapped[str]。
    - created_at: Mapped[datetime]。
    - published_at: Mapped[datetime | None]。
    - attempts: Mapped[int]。
    - last_error: Mapped[str | None]。
    - 方法 from_event()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

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
        """执行 from_event 对应的逻辑，并返回处理结果。

        Args:
            event: Any，调用方传入的 event 参数。

        Returns:
            'OutboxEventRecord'，函数执行后的结果。
        """
        return cls(
            event_id=event.event_id,
            tenant_id=event.tenant_id,
            event_type=event.event_type,
            payload=event.model_dump(mode="json"),
            status="pending",
            created_at=event.occurred_at,
        )


class KnowledgeDocumentRecord(Base):
    """KnowledgeDocumentRecord。

    KnowledgeDocumentRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - __tablename__: 'knowledge_documents'。
    - document_id: Mapped[str]。
    - tenant_id: Mapped[str]。
    - title: Mapped[str]。
    - content: Mapped[str]。
    - source_uri: Mapped[str]。
    - version: Mapped[int]。
    - payload: Mapped[dict]。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    __tablename__ = "knowledge_documents"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text())
    source_uri: Mapped[str] = mapped_column(String(512), default="")
    version: Mapped[int] = mapped_column(default=1)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)


class KnowledgeChunkRecord(Base):
    """KnowledgeChunkRecord。

    KnowledgeChunkRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - __tablename__: 'knowledge_chunks'。
    - chunk_id: Mapped[str]。
    - document_id: Mapped[str]。
    - tenant_id: Mapped[str]。
    - content: Mapped[str]。
    - position: Mapped[int]。
    - payload: Mapped[dict]。
    - embedding: Mapped[list[float] | None]。
    - embedding_model: Mapped[str | None]。
    - embedding_version: Mapped[int | None]。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

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
    """CostRecordRecord。

    CostRecordRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - __tablename__: 'cost_records'。
    - id: Mapped[int]。
    - tenant_id: Mapped[str]。
    - task_id: Mapped[str]。
    - model_name: Mapped[str]。
    - provider: Mapped[str]。
    - input_tokens: Mapped[int]。
    - output_tokens: Mapped[int]。
    - amount: Mapped[float]。
    - created_at: Mapped[datetime]。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

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
    """AuditEventRecord。

    AuditEventRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - __tablename__: 'audit_events'。
    - event_id: Mapped[str]。
    - tenant_id: Mapped[str]。
    - action: Mapped[str]。
    - resource_type: Mapped[str]。
    - resource_id: Mapped[str]。
    - risk_level: Mapped[str]。
    - actor_type: Mapped[str]。
    - actor_id: Mapped[str]。
    - trace_id: Mapped[str | None]。
    - payload: Mapped[dict]。
    - created_at: Mapped[datetime]。
    - 方法 from_domain()。
    - 方法 to_domain()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

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
        """执行 from_domain 对应的逻辑，并返回处理结果。

        Args:
            event: AuditEvent，调用方传入的 event 参数。

        Returns:
            'AuditEventRecord'，函数执行后的结果。
        """
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
        """执行 to_domain 对应的逻辑，并返回处理结果。

        Returns:
            AuditEvent，函数执行后的结果。
        """
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
    """EvaluationSampleRecord。

    EvaluationSampleRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - __tablename__: 'evaluation_samples'。
    - sample_id: Mapped[str]。
    - tenant_id: Mapped[str]。
    - source_ticket_id: Mapped[str]。
    - query: Mapped[str]。
    - draft_text: Mapped[str]。
    - final_text: Mapped[str]。
    - action: Mapped[str]。
    - reason: Mapped[str]。
    - reviewer_id: Mapped[str]。
    - intent: Mapped[str | None]。
    - priority: Mapped[str]。
    - risk_level: Mapped[str]。
    - model_name: Mapped[str]。
    - provider: Mapped[str]。
    - trace_id: Mapped[str]。
    - created_at: Mapped[datetime]。
    - 方法 from_domain()。
    - 方法 to_domain()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

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
        """执行 from_domain 对应的逻辑，并返回处理结果。

        Args:
            sample: EvaluationSample，调用方传入的 sample 参数。

        Returns:
            'EvaluationSampleRecord'，函数执行后的结果。
        """
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
        """执行 to_domain 对应的逻辑，并返回处理结果。

        Returns:
            EvaluationSample，函数执行后的结果。
        """
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
    """GoldenItemRecord。

    GoldenItemRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - __tablename__: 'golden_items'。
    - item_id: Mapped[str]。
    - tenant_id: Mapped[str]。
    - query: Mapped[str]。
    - expected_chunk_ids: Mapped[list]。
    - expected_citations: Mapped[list]。
    - expected_intent: Mapped[str | None]。
    - expected_priority: Mapped[str | None]。
    - expected_risk_level: Mapped[str | None]。
    - created_at: Mapped[datetime]。
    - 方法 from_domain()。
    - 方法 to_domain()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

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
        """执行 from_domain 对应的逻辑，并返回处理结果。

        Args:
            item: GoldenItem，调用方传入的 item 参数。

        Returns:
            'GoldenItemRecord'，函数执行后的结果。
        """
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
        """执行 to_domain 对应的逻辑，并返回处理结果。

        Returns:
            GoldenItem，函数执行后的结果。
        """
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
    """RegressionRunRecord。

    RegressionRunRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - __tablename__: 'regression_runs'。
    - run_id: Mapped[str]。
    - tenant_id: Mapped[str]。
    - candidate_id: Mapped[str]。
    - status: Mapped[str]。
    - recall_at_k: Mapped[float]。
    - citation_accuracy: Mapped[float]。
    - classification_accuracy: Mapped[float]。
    - priority_accuracy: Mapped[float]。
    - structured_output_rate: Mapped[float]。
    - high_risk_miss_rate: Mapped[float]。
    - verdict: Mapped[str]。
    - report: Mapped[dict]。
    - created_at: Mapped[datetime]。
    - 方法 from_domain()。
    - 方法 to_domain()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

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
        """执行 from_domain 对应的逻辑，并返回处理结果。

        Args:
            run: RegressionRun，调用方传入的 run 参数。
            report_dict: dict | None，调用方传入的 report_dict 参数。

        Returns:
            'RegressionRunRecord'，函数执行后的结果。
        """
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
        """执行 to_domain 对应的逻辑，并返回处理结果。

        Returns:
            RegressionRun，函数执行后的结果。
        """
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


class ConnectorSpecRecord(Base):
    """ConnectorSpecRecord。

    ConnectorSpecRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - __tablename__: 'connector_specs'。
    - connector_id: Mapped[str]。
    - tenant_id: Mapped[str]。
    - name: Mapped[str]。
    - kind: Mapped[str]。
    - version: Mapped[str]。
    - risk_level: Mapped[str]。
    - endpoint: Mapped[str | None]。
    - allowed_actions: Mapped[list]。
    - credential: Mapped[dict | None]。
    - config: Mapped[dict]。
    - enabled: Mapped[bool]。
    - created_at: Mapped[datetime]。
    - 方法 from_domain()。
    - 方法 to_domain()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    __tablename__ = "connector_specs"

    connector_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    version: Mapped[str] = mapped_column(String(32), default="1.0")
    risk_level: Mapped[str] = mapped_column(String(16), default="low")
    endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    allowed_actions: Mapped[list] = mapped_column(JSON(), default=list)
    credential: Mapped[dict | None] = mapped_column(JSON(), nullable=True)
    config: Mapped[dict] = mapped_column(JSON(), default=dict)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(cls, spec: ConnectorSpec) -> "ConnectorSpecRecord":
        """执行 from_domain 对应的逻辑，并返回处理结果。

        Args:
            spec: ConnectorSpec，调用方传入的 spec 参数。

        Returns:
            'ConnectorSpecRecord'，函数执行后的结果。
        """
        return cls(
            connector_id=spec.connector_id,
            tenant_id=spec.tenant_id,
            name=spec.name,
            kind=spec.kind.value,
            version=spec.version,
            risk_level=spec.risk_level.value,
            endpoint=spec.endpoint,
            allowed_actions=list(spec.allowed_actions),
            credential=(
                spec.credential.model_dump(mode="json") if spec.credential is not None else None
            ),
            config=spec.config,
            enabled=spec.enabled,
            created_at=spec.created_at,
        )

    def to_domain(self) -> ConnectorSpec:
        """执行 to_domain 对应的逻辑，并返回处理结果。

        Returns:
            ConnectorSpec，函数执行后的结果。
        """
        created_at = self.created_at
        if created_at is not None and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return ConnectorSpec(
            connector_id=self.connector_id,
            tenant_id=self.tenant_id,
            name=self.name,
            kind=ConnectorKind(self.kind),
            version=self.version,
            risk_level=ConnectorRiskLevel(self.risk_level),
            endpoint=self.endpoint,
            allowed_actions=list(self.allowed_actions or []),
            credential=(
                CredentialReference.model_validate(self.credential) if self.credential else None
            ),
            config=self.config,
            enabled=self.enabled,
            created_at=created_at,
        )


class RoleRecord(Base):
    """RoleRecord。

    RoleRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - __tablename__: 'rbac_roles'。
    - role_id: Mapped[str]。
    - tenant_id: Mapped[str]。
    - name: Mapped[str]。
    - description: Mapped[str]。
    - permissions: Mapped[list]。
    - built_in: Mapped[bool]。
    - created_at: Mapped[datetime]。
    - 方法 from_domain()。
    - 方法 to_domain()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    __tablename__ = "rbac_roles"

    role_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="")
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    built_in: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(cls, role: Role) -> "RoleRecord":
        """执行 from_domain 对应的逻辑，并返回处理结果。

        Args:
            role: Role，调用方传入的 role 参数。

        Returns:
            'RoleRecord'，函数执行后的结果。
        """
        return cls(
            role_id=role.role_id,
            tenant_id=role.tenant_id,
            name=role.name,
            description=role.description,
            permissions=[p.value for p in role.permissions],
            built_in=role.built_in,
            created_at=role.created_at,
        )

    def to_domain(self) -> Role:
        """执行 to_domain 对应的逻辑，并返回处理结果。

        Returns:
            Role，函数执行后的结果。
        """
        created_at = self.created_at
        if created_at is not None and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return Role(
            role_id=self.role_id,
            tenant_id=self.tenant_id,
            name=self.name,
            description=self.description,
            permissions=[Permission(p) for p in (self.permissions or [])],
            built_in=self.built_in,
            created_at=created_at,
        )


class RoleAssignmentRecord(Base):
    """RoleAssignmentRecord。

    RoleAssignmentRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - __tablename__: 'rbac_role_assignments'。
    - assignment_id: Mapped[str]。
    - tenant_id: Mapped[str]。
    - user_id: Mapped[str]。
    - role_id: Mapped[str]。
    - granted_at: Mapped[datetime]。
    - 方法 from_domain()。
    - 方法 to_domain()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    __tablename__ = "rbac_role_assignments"

    assignment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    role_id: Mapped[str] = mapped_column(String(64))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(cls, assignment: RoleAssignment) -> "RoleAssignmentRecord":
        """执行 from_domain 对应的逻辑，并返回处理结果。

        Args:
            assignment: RoleAssignment，调用方传入的 assignment 参数。

        Returns:
            'RoleAssignmentRecord'，函数执行后的结果。
        """
        return cls(
            assignment_id=assignment.assignment_id,
            tenant_id=assignment.tenant_id,
            user_id=assignment.user_id,
            role_id=assignment.role_id,
            granted_at=assignment.granted_at,
        )

    def to_domain(self) -> RoleAssignment:
        """执行 to_domain 对应的逻辑，并返回处理结果。

        Returns:
            RoleAssignment，函数执行后的结果。
        """
        granted_at = self.granted_at
        if granted_at is not None and granted_at.tzinfo is None:
            granted_at = granted_at.replace(tzinfo=timezone.utc)
        return RoleAssignment(
            assignment_id=self.assignment_id,
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            role_id=self.role_id,
            granted_at=granted_at,
        )


class TenantQuotaRecord(Base):
    """TenantQuotaRecord。

    TenantQuotaRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - __tablename__: 'tenant_quotas'。
    - tenant_id: Mapped[str]。
    - monthly_limit: Mapped[float]。
    - warning_threshold: Mapped[float]。
    - hard_limit: Mapped[float]。
    - enabled: Mapped[bool]。
    - updated_at: Mapped[datetime]。
    - 方法 from_domain()。
    - 方法 to_domain()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    __tablename__ = "tenant_quotas"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    monthly_limit: Mapped[float] = mapped_column(Float, default=0.0)
    warning_threshold: Mapped[float] = mapped_column(Float, default=0.8)
    hard_limit: Mapped[float] = mapped_column(Float, default=1.0)
    enabled: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(cls, quota: TenantQuota) -> "TenantQuotaRecord":
        """执行 from_domain 对应的逻辑，并返回处理结果。

        Args:
            quota: TenantQuota，调用方传入的 quota 参数。

        Returns:
            'TenantQuotaRecord'，函数执行后的结果。
        """
        return cls(
            tenant_id=quota.tenant_id,
            monthly_limit=quota.monthly_limit,
            warning_threshold=quota.warning_threshold,
            hard_limit=quota.hard_limit,
            enabled=quota.enabled,
            updated_at=quota.updated_at,
        )

    def to_domain(self) -> TenantQuota:
        """执行 to_domain 对应的逻辑，并返回处理结果。

        Returns:
            TenantQuota，函数执行后的结果。
        """
        updated_at = self.updated_at
        if updated_at is not None and updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return TenantQuota(
            tenant_id=self.tenant_id,
            monthly_limit=self.monthly_limit,
            warning_threshold=self.warning_threshold,
            hard_limit=self.hard_limit,
            enabled=self.enabled,
            updated_at=updated_at,
        )


class ScheduledReportRecord(Base):
    """ScheduledReportRecord。

    ScheduledReportRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - __tablename__: 'scheduled_reports'。
    - report_id: Mapped[str]。
    - tenant_id: Mapped[str]。
    - report_type: Mapped[str]。
    - cadence: Mapped[str]。
    - enabled: Mapped[bool]。
    - retention_days: Mapped[int | None]。
    - created_at: Mapped[datetime]。
    - last_run_at: Mapped[datetime | None]。
    - next_run_at: Mapped[datetime]。
    - 方法 from_domain()。
    - 方法 to_domain()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    __tablename__ = "scheduled_reports"

    report_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    report_type: Mapped[str] = mapped_column(String(16))
    cadence: Mapped[str] = mapped_column(String(16), default="daily")
    enabled: Mapped[bool] = mapped_column(default=True)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(cls, report: ScheduledReport) -> "ScheduledReportRecord":
        """执行 from_domain 对应的逻辑，并返回处理结果。

        Args:
            report: ScheduledReport，调用方传入的 report 参数。

        Returns:
            'ScheduledReportRecord'，函数执行后的结果。
        """
        return cls(
            report_id=report.report_id,
            tenant_id=report.tenant_id,
            report_type=report.report_type.value,
            cadence=report.cadence,
            enabled=report.enabled,
            retention_days=report.retention_days,
            created_at=report.created_at,
            last_run_at=report.last_run_at,
            next_run_at=report.next_run_at,
        )

    def to_domain(self) -> ScheduledReport:
        """执行 to_domain 对应的逻辑，并返回处理结果。

        Returns:
            ScheduledReport，函数执行后的结果。
        """

        def _utc(value: datetime | None) -> datetime | None:
            """执行 _utc 对应的逻辑，并返回处理结果。

            Args:
                value: datetime | None，调用方传入的 value 参数。

            Returns:
                datetime | None，函数执行后的结果。
            """
            if value is None:
                return None
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value

        return ScheduledReport(
            report_id=self.report_id,
            tenant_id=self.tenant_id,
            report_type=ReportType(self.report_type),
            cadence=self.cadence,
            enabled=self.enabled,
            retention_days=self.retention_days,
            created_at=_utc(self.created_at) or utc_now(),
            last_run_at=_utc(self.last_run_at),
            next_run_at=_utc(self.next_run_at) or utc_now(),
        )


class ReportRunRecord(Base):
    """ReportRunRecord。

    ReportRunRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - __tablename__: 'report_runs'。
    - run_id: Mapped[str]。
    - tenant_id: Mapped[str]。
    - report_type: Mapped[str]。
    - format: Mapped[str]。
    - rows: Mapped[list]。
    - summary: Mapped[dict]。
    - scheduled_report_id: Mapped[str | None]。
    - generated_at: Mapped[datetime]。
    - archived: Mapped[bool]。
    - 方法 from_domain()。
    - 方法 to_domain()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    __tablename__ = "report_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    report_type: Mapped[str] = mapped_column(String(16), index=True)
    format: Mapped[str] = mapped_column(String(8), default="json")
    rows: Mapped[list] = mapped_column(JSON(), default=list)
    summary: Mapped[dict] = mapped_column(JSON(), default=dict)
    scheduled_report_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    @classmethod
    def from_domain(cls, run: ReportRun) -> "ReportRunRecord":
        """执行 from_domain 对应的逻辑，并返回处理结果。

        Args:
            run: ReportRun，调用方传入的 run 参数。

        Returns:
            'ReportRunRecord'，函数执行后的结果。
        """
        return cls(
            run_id=run.run_id,
            tenant_id=run.tenant_id,
            report_type=run.report_type.value,
            format=run.format.value,
            rows=list(run.rows),
            summary=run.summary,
            scheduled_report_id=run.scheduled_report_id,
            generated_at=run.generated_at,
            archived=run.archived,
        )

    def to_domain(self) -> ReportRun:
        """执行 to_domain 对应的逻辑，并返回处理结果。

        Returns:
            ReportRun，函数执行后的结果。
        """
        generated_at = self.generated_at
        if generated_at is not None and generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        return ReportRun(
            run_id=self.run_id,
            tenant_id=self.tenant_id,
            report_type=ReportType(self.report_type),
            format=ReportFormat(self.format),
            rows=list(self.rows or []),
            summary=dict(self.summary or {}),
            generated_at=generated_at or utc_now(),
            scheduled_report_id=self.scheduled_report_id,
            archived=self.archived,
        )
