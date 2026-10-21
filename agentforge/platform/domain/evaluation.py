"""评估模块。"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from agentforge.platform.domain.priority import PriorityLevel
from agentforge.platform.domain.risk import RiskLevel


class EvaluationSample(BaseModel):
    """评估样本相关组件。

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

    model_config = ConfigDict(extra="forbid")

    sample_id: str
    tenant_id: str
    source_ticket_id: str
    query: str
    draft_text: str
    final_text: str
    action: str
    reason: str = ""
    reviewer_id: str
    intent: str | None = None
    priority: PriorityLevel = PriorityLevel.P3
    risk_level: RiskLevel = RiskLevel.LOW
    model_name: str = ""
    provider: str = ""
    trace_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
