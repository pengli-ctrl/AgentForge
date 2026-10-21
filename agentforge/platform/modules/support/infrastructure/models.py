"""数据模型模块。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from agentforge.platform.domain.risk import RiskLevel
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.db.models import utc_now
from agentforge.platform.modules.support.domain.ticket import Ticket, TicketPriority, TicketStatus


class TicketRecord(Base):
    """工单记录持久化模型。

    Attributes:
        ticket_id: 工单ID。
        tenant_id: 租户 ID，用于数据隔离。
        customer_id: 客户ID。
        conversation_id: 会话ID。
        source: 调用或事件来源。
        subject: 字段值。
        status: 当前状态。
        priority: 优先级。
        intent: 字段值。
        product: 字段值。
        assigned_team: 字段值。
        assignee_id: 处理人ID。
        risk_level: 风险级别。
        confidence: 字段值。
        idempotency_key: 幂等键，用于避免重复处理。
        payload: 事件、工作流或请求载荷。
        created_at: 创建时间。
        updated_at: 更新时间。
        version: 版本号。
    """

    __tablename__ = "support_tickets"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_support_tickets_tenant_idempotency"
        ),
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
    assignee_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    risk_level: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    version: Mapped[int] = mapped_column(default=1)

    @classmethod
    def from_domain(cls, ticket: Ticket) -> "TicketRecord":
        """将持久化记录转换为领域对象。

        Args:
            ticket: 客服工单对象。

        Returns:
            处理结果对象。
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
            assignee_id=ticket.assignee_id,
            risk_level=ticket.risk_level.value,
            confidence=ticket.confidence,
            idempotency_key=ticket.idempotency_key,
            payload=ticket.metadata,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            version=ticket.version,
        )

    def apply_domain(self, ticket: Ticket) -> None:
        """应用领域。

        Args:
            ticket: 客服工单对象。
        """
        self.customer_id = ticket.customer_id
        self.conversation_id = ticket.conversation_id
        self.subject = ticket.subject
        self.status = ticket.status.value
        self.priority = ticket.priority.value
        self.intent = ticket.intent
        self.product = ticket.product
        self.assigned_team = ticket.assigned_team
        self.assignee_id = ticket.assignee_id
        self.risk_level = ticket.risk_level.value
        self.confidence = ticket.confidence
        self.idempotency_key = ticket.idempotency_key
        self.payload = ticket.metadata
        self.updated_at = ticket.updated_at
        self.version = ticket.version

    def to_domain(self) -> Ticket:
        """转换领域。

        Returns:
            工单结果。
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
            assignee_id=self.assignee_id,
            risk_level=RiskLevel(self.risk_level),
            confidence=self.confidence,
            idempotency_key=self.idempotency_key,
            metadata=self.payload or {},
            created_at=self.created_at,
            updated_at=self.updated_at,
            version=self.version,
        )
