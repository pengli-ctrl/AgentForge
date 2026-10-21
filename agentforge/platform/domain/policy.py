"""策略模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ValidationOutcome(str, Enum):
    """校验状态枚举。"""

    ALLOWED = "allowed"
    DENIED = "denied"
    REQUIRES_APPROVAL = "requires_approval"


class PolicyDecision(BaseModel):
    """策略决策领域组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        principal: 字段值。
        action: 操作。
        resource_type: 资源类型。
        resource_id: 资源ID。
        outcome: 结果。
        risk_level: 风险级别。
        reasons: 字段值。
        evaluated_at: 于。
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
        """返回允许。

        Returns:
            操作是否成功。
        """
        return self.outcome == ValidationOutcome.ALLOWED


class ActionPolicy(BaseModel):
    """操作策略相关组件。

    Attributes:
        name: 名称。
        tenant_id: 租户 ID，用于数据隔离。
        action: 操作。
        risk_level: 风险级别。
        allowed_roles: 允许角色。
        required_permission: 必需权限。
        require_approval: 要求审批。
        enabled: 是否启用。
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
    """关系相关组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        object_type: 对象。
        object_id: 对象ID。
        relation: 关系。
        subject_type: 字段值。
        subject_id: ID。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    object_type: str
    object_id: str
    relation: str
    subject_type: str
    subject_id: str


class PolicyFileLoader:
    """策略文件加载器相关组件。"""

    @staticmethod
    def parse(text: str) -> list[ActionPolicy]:
        """解析策略文件加载器。

        Args:
            text: 待处理文本。

        Returns:
            结果列表。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
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
        """从字符串构造当前对象。

        Args:
            text: 待处理文本。

        Returns:
            结果列表。
        """
        return cls.parse(text)
