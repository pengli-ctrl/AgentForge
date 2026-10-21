"""配置模块。"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_INTENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class SupportIntentRouteConfig(BaseModel):
    """客服路由配置模型。

    Attributes:
        assigned_team: 字段值。
        queue: 队列。
        assignee_id: 处理人ID。
        sla_minutes: SLA。
        priority: 优先级。
    """

    model_config = ConfigDict(extra="forbid")

    assigned_team: str = Field(min_length=1)
    queue: str = ""
    assignee_id: str = ""
    sla_minutes: int | None = Field(default=None, gt=0)
    priority: Literal["p0", "p1", "p2", "p3"] | None = None

    @field_validator("assigned_team", "queue", "assignee_id")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        """处理去除文本。

        Args:
            value: 待处理值。

        Returns:
            字符串结果。
        """
        return value.strip()


class SupportModuleConfig(BaseModel):
    """客服模块配置模型。

    Attributes:
        default_sla_minutes: 默认SLA。
        sla_due_soon_seconds: SLA到期。
        invoice_gate_team: 发票门禁。
        invoice_gate_assignee: 发票门禁。
        sla_sweep_minutes: SLA扫描。
        sla_escalation_assignee: SLA升级。
        notification_target: 通知目标。
        invoice_gate_sla_minutes: 发票门禁SLA。
        default_team: 默认。
        default_queue: 默认队列。
        intent_routes: 路由。
    """

    model_config = ConfigDict(extra="forbid")

    default_sla_minutes: int = Field(default=480, gt=0)
    sla_due_soon_seconds: int = Field(default=900, ge=0)
    invoice_gate_team: str = Field(default="finance-invoice-gate", min_length=1)
    invoice_gate_assignee: str = ""
    sla_sweep_minutes: float = Field(default=5.0, ge=0)
    sla_escalation_assignee: str = ""
    notification_target: str = ""
    invoice_gate_sla_minutes: int = Field(default=60, gt=0)
    default_team: str = Field(default="support", min_length=1)
    default_queue: str = ""
    intent_routes: dict[str, SupportIntentRouteConfig] = Field(default_factory=dict)

    @field_validator(
        "invoice_gate_team",
        "invoice_gate_assignee",
        "sla_escalation_assignee",
        "notification_target",
        "default_team",
        "default_queue",
    )
    @classmethod
    def _strip_text(cls, value: str) -> str:
        """处理去除文本。

        Args:
            value: 待处理值。

        Returns:
            字符串结果。
        """
        return value.strip()

    @field_validator("intent_routes")
    @classmethod
    def _validate_intent_routes(
        cls, value: dict[str, SupportIntentRouteConfig]
    ) -> dict[str, SupportIntentRouteConfig]:
        """校验路由。

        Args:
            value: 待处理值。

        Returns:
            结构化结果字典。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        for intent in value:
            if not _INTENT_PATTERN.fullmatch(intent):
                raise ValueError(f"invalid intent route key: {intent!r}")
        return value


def default_support_config() -> SupportModuleConfig:
    """创建默认客服配置。

    Returns:
        客服模块配置结果。
    """
    return SupportModuleConfig()


__all__ = [
    "SupportIntentRouteConfig",
    "SupportModuleConfig",
    "default_support_config",
]
