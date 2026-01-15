"""AgentForge 平台领域模型层：approval。

本模块定义 approval 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：ApprovalStatus、Approval。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from agentforge.platform.domain.ticket import RiskLevel


class ApprovalStatus(str, Enum):
    """ApprovalStatus。

    ApprovalStatus 是状态或类型枚举，用于约束系统内部取值，避免使用散落的字符串常量。

    主要成员：
    - PENDING: 'pending'。
    - APPROVED: 'approved'。
    - REJECTED: 'rejected'。
    - EXPIRED: 'expired'。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Approval(BaseModel):
    """Approval。

    Approval 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - approval_id: str。
    - tenant_id: str。
    - ticket_id: str。
    - task_id: str。
    - risk_level: RiskLevel。
    - status: ApprovalStatus。
    - requested_at: datetime。
    - decided_at: datetime | None。
    - decided_by: str | None。
    - reason: str。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    approval_id: str
    tenant_id: str
    ticket_id: str
    task_id: str
    risk_level: RiskLevel
    status: ApprovalStatus = ApprovalStatus.PENDING
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decided_at: datetime | None = None
    decided_by: str | None = None
    reason: str = ""
