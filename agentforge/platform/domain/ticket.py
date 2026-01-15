"""AgentForge 平台领域模型层：ticket。

本模块定义 ticket 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：TicketStatus、TicketPriority、RiskLevel、Ticket。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TicketStatus(str, Enum):
    """TicketStatus。

    TicketStatus 是状态或类型枚举，用于约束系统内部取值，避免使用散落的字符串常量。

    主要成员：
    - NEW: 'new'。
    - CLASSIFYING: 'classifying'。
    - WAITING_REVIEW: 'waiting_review'。
    - WAITING_APPROVAL: 'waiting_approval'。
    - READY_TO_PUBLISH: 'ready_to_publish'。
    - PUBLISHED: 'published'。
    - ESCALATED: 'escalated'。
    - FAILED: 'failed'。
    - CANCELLED: 'cancelled'。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

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
    """TicketPriority。

    TicketPriority 是状态或类型枚举，用于约束系统内部取值，避免使用散落的字符串常量。

    主要成员：
    - P0: 'p0'。
    - P1: 'p1'。
    - P2: 'p2'。
    - P3: 'p3'。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    P0 = "p0"
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"


class RiskLevel(str, Enum):
    """RiskLevel。

    RiskLevel 是状态或类型枚举，用于约束系统内部取值，避免使用散落的字符串常量。

    主要成员：
    - READ_ONLY: 'read_only'。
    - LOW: 'low'。
    - MEDIUM: 'medium'。
    - HIGH: 'high'。
    - CRITICAL: 'critical'。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    READ_ONLY = "read_only"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# 常量：ALLOWED_TRANSITIONS。
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
    """Ticket。

    Ticket 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - ticket_id: str。
    - tenant_id: str。
    - customer_id: str | None。
    - conversation_id: str | None。
    - source: str。
    - subject: str。
    - status: TicketStatus。
    - priority: TicketPriority。
    - intent: str | None。
    - product: str | None。
    - assigned_team: str | None。
    - risk_level: RiskLevel。
    - confidence: float | None。
    - idempotency_key: str。
    - metadata: dict[str, Any]。
    - created_at: datetime。
    - updated_at: datetime。
    - version: int。
    - 方法 can_transition_to()。
    - 方法 transition_to()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

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
        """执行 can_transition_to 对应的逻辑，并返回处理结果。

        Args:
            new_status: TicketStatus，调用方传入的 new_status 参数。

        Returns:
            bool，函数执行后的结果。
        """
        return new_status in ALLOWED_TRANSITIONS[self.status]

    def transition_to(self, new_status: TicketStatus) -> None:
        """执行 transition_to 对应的逻辑，并返回处理结果。

        Args:
            new_status: TicketStatus，调用方传入的 new_status 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if not self.can_transition_to(new_status):
            raise ValueError("Invalid ticket transition")
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
        self.version += 1
