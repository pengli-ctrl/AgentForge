"""工单模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agentforge.platform.domain.priority import PriorityLevel
from agentforge.platform.domain.risk import RiskLevel


class TicketStatus(str, Enum):
    """工单状态枚举。"""

    NEW = "new"
    CLASSIFYING = "classifying"
    WAITING_REVIEW = "waiting_review"
    WAITING_APPROVAL = "waiting_approval"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHED = "published"
    ESCALATED = "escalated"
    FAILED = "failed"
    CANCELLED = "cancelled"


TicketPriority = PriorityLevel


# 常量：ALLOWED_TRANSITIONS。
ALLOWED_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
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
    """工单领域组件。

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
        metadata: 附加元数据。
        created_at: 创建时间。
        updated_at: 更新时间。
        version: 版本号。
    """

    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    tenant_id: str
    customer_id: str | None = None
    conversation_id: str | None = None
    source: str
    subject: str = ""
    status: TicketStatus = TicketStatus.NEW
    priority: PriorityLevel = PriorityLevel.P3
    intent: str | None = None
    product: str | None = None
    assigned_team: str | None = None
    assignee_id: str | None = None
    risk_level: RiskLevel = RiskLevel.READ_ONLY
    confidence: float | None = None
    idempotency_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1

    def can_transition_to(self, new_status: TicketStatus) -> bool:
        """判断可以状态转换到是否成立。

        Args:
            new_status: 状态。

        Returns:
            操作是否成功。
        """
        return new_status in ALLOWED_TRANSITIONS[self.status]

    def transition_to(self, new_status: TicketStatus) -> None:
        """迁移到。

        Args:
            new_status: 状态。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if not self.can_transition_to(new_status):
            raise ValueError("Invalid ticket transition")
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
