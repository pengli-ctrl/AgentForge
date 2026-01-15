"""AgentForge 平台领域模型层：policy。

本模块定义 policy 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：ValidationOutcome、PolicyDecision、ActionPolicy、RelationTuple、PolicyFileLoader。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ValidationOutcome(str, Enum):
    """ValidationOutcome。

    ValidationOutcome 是状态或类型枚举，用于约束系统内部取值，避免使用散落的字符串常量。

    主要成员：
    - ALLOWED: 'allowed'。
    - DENIED: 'denied'。
    - REQUIRES_APPROVAL: 'requires_approval'。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_APPROVAL = "requires_approval"


class PolicyDecision(BaseModel):
    """PolicyDecision。

    PolicyDecision 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - tenant_id: str。
    - principal: str。
    - action: str。
    - resource_type: str。
    - resource_id: str。
    - outcome: ValidationOutcome。
    - risk_level: str。
    - reasons: list[str]。
    - evaluated_at: datetime。
    - 方法 allowed()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    principal: str
    action: str
    resource_type: str = ""
    resource_id: str = ""
    outcome: ValidationOutcome
    risk_level: str = "low"
    reasons: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def allowed(self) -> bool:
        """执行 allowed 对应的逻辑，并返回处理结果。

        Returns:
            bool，函数执行后的结果。
        """
        return self.outcome == ValidationOutcome.ALLOWED


class ActionPolicy(BaseModel):
    """ActionPolicy。

    ActionPolicy 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - name: str。
    - tenant_id: str。
    - action: str。
    - risk_level: str。
    - allowed_roles: list[str]。
    - required_permission: str | None。
    - require_approval: bool。
    - enabled: bool。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    tenant_id: str
    action: str
    risk_level: str = "medium"
    allowed_roles: list[str] = Field(default_factory=list)
    required_permission: str | None = None
    require_approval: bool = False
    enabled: bool = True


class RelationTuple(BaseModel):
    """RelationTuple。

    RelationTuple 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - tenant_id: str。
    - object_type: str。
    - object_id: str。
    - relation: str。
    - subject_type: str。
    - subject_id: str。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    object_type: str
    object_id: str
    relation: str
    subject_type: str
    subject_id: str


class PolicyFileLoader:
    """PolicyFileLoader。

    PolicyFileLoader 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 parse()。
    - 方法 from_string()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    @staticmethod
    def parse(text: str) -> list[ActionPolicy]:
        """执行 parse 对应的逻辑，并返回处理结果。

        Args:
            text: str，调用方传入的 text 参数。

        Returns:
            list[ActionPolicy]，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        import json

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:  # pragma: no cover - trivial path
            raise ValueError(f"policy document is not valid JSON: {exc}") from exc
        if not isinstance(data, list):
            raise ValueError("policy document must be a list of policies")
        return [ActionPolicy.model_validate(item) for item in data]

    @classmethod
    def from_string(cls, text: str) -> list[ActionPolicy]:
        """执行 from_string 对应的逻辑，并返回处理结果。

        Args:
            text: str，调用方传入的 text 参数。

        Returns:
            list[ActionPolicy]，函数执行后的结果。
        """
        return cls.parse(text)
