"""数据模型模块。"""

from __future__ import annotations

from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
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
from agentforge.platform.domain.priority import PriorityLevel
from agentforge.platform.domain.rbac import Role, RoleAssignment
from agentforge.platform.domain.regression import GoldenItem, RegressionRun, RegressionRunStatus
from agentforge.platform.domain.reporting import (
    ReportFormat,
    ReportRun,
    ReportType,
    ScheduledReport,
)
from agentforge.platform.domain.risk import RiskLevel
from agentforge.platform.domain.tenant_quota import TenantQuota
from agentforge.platform.domain.upload import UploadedPart, UploadSession, UploadSessionStatus
from agentforge.platform.infrastructure.db.base import Base


def utc_now() -> datetime:
    """处理UTC。

    Returns:
        处理结果对象。
    """
    return datetime.now(timezone.utc)


class OutboxEventRecord(Base):
    """Outbox事件记录持久化模型。

    Attributes:
        event_id: 事件 ID。
        tenant_id: 租户 ID，用于数据隔离。
        event_type: 事件。
        payload: 事件、工作流或请求载荷。
        status: 当前状态。
        created_at: 创建时间。
        published_at: 已发布于。
        attempts: 字段值。
        last_error: 错误。
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
        """从事件构造当前对象。

        Args:
            event: 待处理事件。

        Returns:
            事件结果。
        """
        return cls(
            event_id=event.event_id,
            tenant_id=event.tenant_id,
            event_type=event.event_type,
            payload=event.model_dump(mode="json"),
            status="pending",
            created_at=event.occurred_at,
        )


class OutboxHandlerReceiptRecord(Base):
    """Outboxhandlerreceipt记录持久化模型。

    Attributes:
        event_id: 事件 ID。
        handler_name: 处理器名称。
        status: 当前状态。
        claimed_at: 于。
        processed_at: 于。
        last_error: 错误。
    """

    __tablename__ = "outbox_handler_receipts"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    handler_name: Mapped[str] = mapped_column(String(256), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="processing", index=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text(), nullable=True)


class KnowledgeDocumentRecord(Base):
    """知识文档记录持久化模型。

    Attributes:
        document_id: 文档ID。
        tenant_id: 租户 ID，用于数据隔离。
        title: 标题。
        content: 写入内容。
        source_uri: 来源URI。
        version: 版本号。
        payload: 事件、工作流或请求载荷。
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
    """知识分块记录相关组件。

    Attributes:
        chunk_id: 分块ID。
        document_id: 文档ID。
        tenant_id: 租户 ID，用于数据隔离。
        content: 写入内容。
        position: 位置。
        payload: 事件、工作流或请求载荷。
        embedding: 字段值。
        embedding_model: 模型。
        embedding_version: 版本。
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
    """成本记录相关组件。

    Attributes:
        id: 唯一标识。
        tenant_id: 租户 ID，用于数据隔离。
        task_id: 任务ID。
        model_name: 模型名称。
        provider: 提供方。
        input_tokens: 输入。
        output_tokens: 输出。
        amount: 金额。
        created_at: 创建时间。
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
    """审计事件记录持久化模型。

    Attributes:
        event_id: 事件 ID。
        tenant_id: 租户 ID，用于数据隔离。
        action: 操作。
        resource_type: 资源类型。
        resource_id: 资源ID。
        risk_level: 风险级别。
        actor_type: 参与者类型。
        actor_id: 执行操作的参与者 ID。
        trace_id: 链路ID。
        payload: 事件、工作流或请求载荷。
        created_at: 创建时间。
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
        """将持久化记录转换为领域对象。

        Args:
            event: 待处理事件。

        Returns:
            事件结果。
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
        """转换领域。

        Returns:
            审计事件结果。
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
    """评估样本记录相关组件。

    Attributes:
        sample_id: 样本ID。
        tenant_id: 租户 ID，用于数据隔离。
        source_ticket_id: 来源工单ID。
        query: 查询。
        draft_text: 草稿文本。
        final_text: 最终文本。
        action: 操作。
        reason: 变更原因。
        reviewer_id: 审核人ID。
        intent: 字段值。
        priority: 优先级。
        risk_level: 风险级别。
        model_name: 模型名称。
        provider: 提供方。
        trace_id: 链路ID。
        created_at: 创建时间。
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
        """将持久化记录转换为领域对象。

        Args:
            sample: 评估样本。

        Returns:
            样本结果。
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
        """转换领域。

        Returns:
            评估样本结果。
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
            priority=PriorityLevel(self.priority),
            risk_level=RiskLevel(self.risk_level),
            model_name=self.model_name,
            provider=self.provider,
            trace_id=self.trace_id,
            created_at=self.created_at,
        )


class GoldenItemRecord(Base):
    """基准条目记录相关组件。

    Attributes:
        item_id: 条目ID。
        tenant_id: 租户 ID，用于数据隔离。
        query: 查询。
        expected_chunk_ids: 分块。
        expected_citations: 引用。
        expected_intent: 字段值。
        expected_priority: 优先级。
        expected_risk_level: 风险级别。
        created_at: 创建时间。
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
        """将持久化记录转换为领域对象。

        Args:
            item: 条目。

        Returns:
            条目结果。
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
        """转换领域。

        Returns:
            基准条目结果。
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
    """回归运行记录相关组件。

    Attributes:
        run_id: 运行ID。
        tenant_id: 租户 ID，用于数据隔离。
        candidate_id: 候选结果ID。
        status: 当前状态。
        recall_at_k: 召回于K。
        citation_accuracy: 引用准确率。
        classification_accuracy: 分类准确率。
        priority_accuracy: 优先级准确率。
        structured_output_rate: 结构化输出速率。
        high_risk_miss_rate: 高风险速率。
        verdict: 字段值。
        report: 报告。
        created_at: 创建时间。
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
        """将持久化记录转换为领域对象。

        Args:
            run: 运行。
            report_dict: 报告字典。

        Returns:
            运行结果。
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
        """转换领域。

        Returns:
            回归运行结果。
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
    """规格记录相关组件。

    Attributes:
        connector_id: 连接器ID。
        tenant_id: 租户 ID，用于数据隔离。
        name: 名称。
        kind: 资源种类。
        version: 版本号。
        risk_level: 风险级别。
        endpoint: 端点。
        allowed_actions: 允许操作。
        credential: 凭据。
        config: 组件配置。
        enabled: 是否启用。
        created_at: 创建时间。
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
        """将持久化记录转换为领域对象。

        Args:
            spec: 资源规格定义。

        Returns:
            规格结果。
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
        """转换领域。

        Returns:
            连接器规格结果。
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
    """角色记录持久化模型。

    Attributes:
        role_id: 角色ID。
        tenant_id: 租户 ID，用于数据隔离。
        name: 名称。
        description: 描述信息。
        permissions: 权限。
        built_in: 在。
        created_at: 创建时间。
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
        """将持久化记录转换为领域对象。

        Args:
            role: 角色。

        Returns:
            处理结果对象。
        """
        return cls(
            role_id=role.role_id,
            tenant_id=role.tenant_id,
            name=role.name,
            description=role.description,
            permissions=[str(permission) for permission in role.permissions],
            built_in=role.built_in,
            created_at=role.created_at,
        )

    def to_domain(self) -> Role:
        """转换领域。

        Returns:
            角色结果。
        """
        created_at = self.created_at
        if created_at is not None and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return Role(
            role_id=self.role_id,
            tenant_id=self.tenant_id,
            name=self.name,
            description=self.description,
            permissions=[str(permission) for permission in (self.permissions or [])],
            built_in=self.built_in,
            created_at=created_at,
        )


class RoleAssignmentRecord(Base):
    """角色分配记录相关组件。

    Attributes:
        assignment_id: 分配ID。
        tenant_id: 租户 ID，用于数据隔离。
        user_id: 用户ID。
        role_id: 角色ID。
        granted_at: 于。
    """

    __tablename__ = "rbac_role_assignments"

    assignment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    role_id: Mapped[str] = mapped_column(String(64))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @classmethod
    def from_domain(cls, assignment: RoleAssignment) -> "RoleAssignmentRecord":
        """将持久化记录转换为领域对象。

        Args:
            assignment: 分配。

        Returns:
            分配结果。
        """
        return cls(
            assignment_id=assignment.assignment_id,
            tenant_id=assignment.tenant_id,
            user_id=assignment.user_id,
            role_id=assignment.role_id,
            granted_at=assignment.granted_at,
        )

    def to_domain(self) -> RoleAssignment:
        """转换领域。

        Returns:
            角色分配结果。
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
    """租户配额记录持久化模型。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        monthly_limit: 月度限制。
        warning_threshold: 警告阈值。
        hard_limit: 硬限制。
        enabled: 是否启用。
        updated_at: 更新时间。
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
        """将持久化记录转换为领域对象。

        Args:
            quota: 配额配置。

        Returns:
            配额结果。
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
        """转换领域。

        Returns:
            租户配额结果。
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
    """报告记录相关组件。

    Attributes:
        report_id: 报告ID。
        tenant_id: 租户 ID，用于数据隔离。
        report_type: 报告。
        cadence: 周期。
        enabled: 是否启用。
        retention_days: 保留。
        created_at: 创建时间。
        last_run_at: 运行于。
        next_run_at: 下一个运行于。
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
        """将持久化记录转换为领域对象。

        Args:
            report: 报告。

        Returns:
            报告结果。
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
        """转换领域。

        Returns:
            报告结果。
        """

        def _utc(value: datetime | None) -> datetime | None:
            """处理UTC。

            Args:
                value: 待处理值。

            Returns:
                无结果。
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
    """报告运行记录相关组件。

    Attributes:
        run_id: 运行ID。
        tenant_id: 租户 ID，用于数据隔离。
        report_type: 报告。
        format: 格式化。
        rows: 字段值。
        summary: 摘要。
        scheduled_report_id: 报告ID。
        generated_at: 于。
        archived: 已归档。
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
        """将持久化记录转换为领域对象。

        Args:
            run: 运行。

        Returns:
            运行结果。
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
        """转换领域。

        Returns:
            报告运行结果。
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


class UploadSessionRecord(Base):
    """上传会话记录持久化模型。

    Attributes:
        upload_id: 上传ID。
        tenant_id: 租户 ID，用于数据隔离。
        owner_module: 模块。
        filename: 字段值。
        content_type: 内容。
        size_bytes: 大小。
        chunk_size: 分块大小。
        total_chunks: 总计分片。
        status: 当前状态。
        expected_sha256: 字段值。
        completed_sha256: 已完成。
        object_key: 对象键。
        parts: 分片。
        created_at: 创建时间。
        updated_at: 更新时间。
        expires_at: 于。
    """

    __tablename__ = "upload_sessions"

    upload_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    owner_module: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer())
    chunk_size: Mapped[int] = mapped_column(Integer())
    total_chunks: Mapped[int] = mapped_column(Integer())
    status: Mapped[str] = mapped_column(String(32), index=True)
    expected_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    parts: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    @classmethod
    def from_domain(cls, session: UploadSession) -> "UploadSessionRecord":
        """将持久化记录转换为领域对象。

        Args:
            session: 当前会话。

        Returns:
            会话结果。
        """
        return cls(
            upload_id=session.upload_id,
            tenant_id=session.tenant_id,
            owner_module=session.owner_module,
            filename=session.filename,
            content_type=session.content_type,
            size_bytes=session.size_bytes,
            chunk_size=session.chunk_size,
            total_chunks=session.total_chunks,
            status=session.status.value,
            expected_sha256=session.expected_sha256,
            completed_sha256=session.completed_sha256,
            object_key=session.object_key,
            parts=[part.model_dump(mode="json") for part in session.parts],
            created_at=session.created_at,
            updated_at=session.updated_at,
            expires_at=session.expires_at,
        )

    def apply_domain(self, session: UploadSession) -> None:
        """应用领域。

        Args:
            session: 当前会话。
        """
        self.status = session.status.value
        self.expected_sha256 = session.expected_sha256
        self.completed_sha256 = session.completed_sha256
        self.object_key = session.object_key
        self.parts = [part.model_dump(mode="json") for part in session.parts]
        self.updated_at = session.updated_at
        self.expires_at = session.expires_at

    def to_domain(self) -> UploadSession:
        """转换领域。

        Returns:
            上传会话结果。
        """
        return UploadSession(
            upload_id=self.upload_id,
            tenant_id=self.tenant_id,
            owner_module=self.owner_module,
            filename=self.filename,
            content_type=self.content_type,
            size_bytes=self.size_bytes,
            chunk_size=self.chunk_size,
            total_chunks=self.total_chunks,
            status=UploadSessionStatus(self.status),
            expected_sha256=self.expected_sha256,
            completed_sha256=self.completed_sha256,
            object_key=self.object_key,
            parts=[UploadedPart.model_validate(part) for part in self.parts or []],
            created_at=_as_utc(self.created_at),
            updated_at=_as_utc(self.updated_at),
            expires_at=_as_utc(self.expires_at),
        )


def _as_utc(value: datetime) -> datetime:
    """处理作为UTC。

    Args:
        value: 待处理值。

    Returns:
        处理结果对象。
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
