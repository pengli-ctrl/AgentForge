"""AgentForge 平台领域模型层：evaluation。

本模块定义 evaluation 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：EvaluationSample。
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from agentforge.platform.domain.ticket import RiskLevel, TicketPriority


class EvaluationSample(BaseModel):
    """EvaluationSample。

    EvaluationSample 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - sample_id: str。
    - tenant_id: str。
    - source_ticket_id: str。
    - query: str。
    - draft_text: str。
    - final_text: str。
    - action: str。
    - reason: str。
    - reviewer_id: str。
    - intent: str | None。
    - priority: TicketPriority。
    - risk_level: RiskLevel。
    - model_name: str。
    - provider: str。
    - trace_id: str。
    - created_at: datetime。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
    priority: TicketPriority = TicketPriority.P3
    risk_level: RiskLevel = RiskLevel.LOW
    model_name: str = ""
    provider: str = ""
    trace_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
