"""套餐模块。"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentforge.platform.domain.usage import UsageMetric
from agentforge.platform.settings import Settings

OveragePolicy = Literal["block", "warn", "allow"]


class PlanDefinition(BaseModel):
    """套餐定义领域组件。

    Attributes:
        name: 名称。
        display_name: 名称。
        modules: 模块。
        module_configs: 模块。
        metric_limits: 字段值。
        unit_prices_cents: 分。
        base_fee_cents: 基础分。
        retention_days: 保留。
        automation_quota: 配额。
        overage_policy: 策略。
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    display_name: str
    modules: tuple[str, ...]
    module_configs: dict[str, dict[str, object]] = Field(default_factory=dict)
    metric_limits: dict[UsageMetric, int] = Field(default_factory=dict)
    unit_prices_cents: dict[UsageMetric, float] = Field(default_factory=dict)
    base_fee_cents: int = Field(default=0, ge=0)
    retention_days: int = Field(default=30, ge=1)
    automation_quota: int = Field(default=1000, ge=0)
    overage_policy: OveragePolicy = "warn"

    def limit_for(self, metric: UsageMetric) -> int:
        """处理限制用于。

        Args:
            metric: 用量指标。

        Returns:
            整数结果。
        """
        return max(0, int(self.metric_limits.get(metric, 0)))

    def is_unlimited(self, metric: UsageMetric) -> bool:
        """判断无限制是否成立。

        Args:
            metric: 用量指标。

        Returns:
            操作是否成功。
        """
        return self.limit_for(metric) == 0


class PlanCatalog:
    """计划目录相关组件。"""

    def __init__(self, plans: list[PlanDefinition], default_plan: str = "starter") -> None:
        """初始化 PlanCatalog。

        Args:
            plans: 套餐。
            default_plan: 默认计划。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        self._plans = {plan.name: plan for plan in plans}
        if default_plan not in self._plans:
            raise ValueError(f"default plan is not defined: {default_plan}")
        self.default_plan = default_plan

    @classmethod
    def default(cls) -> "PlanCatalog":
        """处理默认。

        Returns:
            处理结果对象。
        """
        return cls(_default_plans())

    @classmethod
    def from_settings(cls, settings: Settings) -> "PlanCatalog":
        """从配置构造当前对象。

        Args:
            settings: 应用配置。

        Returns:
            处理结果对象。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        plans = {plan.name: plan for plan in _default_plans()}
        if settings.saas_plans_json.strip():
            raw = json.loads(settings.saas_plans_json)
            if not isinstance(raw, list):
                raise ValueError("AGENTFORGE_SAAS_PLANS_JSON must be a JSON array")
            for item in raw:
                plan = PlanDefinition.model_validate(item)
                plans[plan.name] = plan
        return cls(list(plans.values()), default_plan=settings.saas_default_plan)

    def get(self, name: str) -> PlanDefinition:
        """获取计划目录。

        Args:
            name: 资源或对象名称。

        Returns:
            计划结果。

        Raises:
            KeyError: 缺少必要配置或目标对象时抛出。
        """
        plan = self._plans.get(name)
        if plan is None:
            raise KeyError(f"unknown plan: {name}")
        return plan

    def list_plans(self) -> tuple[PlanDefinition, ...]:
        """查询套餐。

        Returns:
            结果元组。
        """
        return tuple(self._plans.values())

    def public(self) -> list[dict[str, object]]:
        """处理公共。

        Returns:
            结果列表。
        """
        return [plan.model_dump(mode="json") for plan in self._plans.values()]


def _default_plans() -> list[PlanDefinition]:
    """处理默认套餐。

    Returns:
        结果列表。
    """
    metrics = list(UsageMetric)
    unlimited = {metric: 0 for metric in metrics}
    return [
        PlanDefinition(
            name="starter",
            display_name="Starter",
            modules=("support",),
            module_configs={"support": {"default_sla_minutes": 480, "sla_due_soon_seconds": 900}},
            metric_limits={
                UsageMetric.OCR_PAGES: 50,
                UsageMetric.MODEL_TOKENS: 100_000,
                UsageMetric.WORKFLOW_EXECUTIONS: 1_000,
                UsageMetric.STORAGE_BYTES: 1_073_741_824,
                UsageMetric.NOTIFICATION_COUNT: 1_000,
            },
            unit_prices_cents={
                UsageMetric.OCR_PAGES: 2.0,
                UsageMetric.MODEL_TOKENS: 0.002,
                UsageMetric.WORKFLOW_EXECUTIONS: 0.5,
                UsageMetric.STORAGE_BYTES: 0.000000001,
                UsageMetric.NOTIFICATION_COUNT: 0.1,
            },
            base_fee_cents=49_900,
            retention_days=30,
            automation_quota=1_000,
            overage_policy="warn",
        ),
        PlanDefinition(
            name="professional",
            display_name="Professional",
            modules=("support", "expense"),
            module_configs={
                "support": {"default_sla_minutes": 240, "sla_due_soon_seconds": 1800},
                "expense": {"invoice_enforcement": "verified"},
            },
            metric_limits={
                UsageMetric.OCR_PAGES: 2_000,
                UsageMetric.MODEL_TOKENS: 5_000_000,
                UsageMetric.WORKFLOW_EXECUTIONS: 50_000,
                UsageMetric.STORAGE_BYTES: 53_687_091_200,
                UsageMetric.NOTIFICATION_COUNT: 50_000,
            },
            unit_prices_cents={
                UsageMetric.OCR_PAGES: 1.0,
                UsageMetric.MODEL_TOKENS: 0.001,
                UsageMetric.WORKFLOW_EXECUTIONS: 0.2,
                UsageMetric.STORAGE_BYTES: 0.0000000005,
                UsageMetric.NOTIFICATION_COUNT: 0.05,
            },
            base_fee_cents=199_900,
            retention_days=180,
            automation_quota=50_000,
            overage_policy="allow",
        ),
        PlanDefinition(
            name="enterprise",
            display_name="Enterprise",
            modules=("support", "expense", "asset"),
            module_configs={
                "support": {"default_sla_minutes": 120, "sla_due_soon_seconds": 3600},
                "expense": {"invoice_enforcement": "strict"},
            },
            metric_limits=unlimited,
            base_fee_cents=999_900,
            retention_days=365,
            automation_quota=500_000,
            overage_policy="allow",
        ),
        PlanDefinition(
            name="private",
            display_name="Private Deployment",
            modules=("support", "expense", "asset"),
            module_configs={
                "support": {"default_sla_minutes": 480, "sla_due_soon_seconds": 900},
            },
            metric_limits=unlimited,
            base_fee_cents=0,
            retention_days=3650,
            automation_quota=0,
            overage_policy="allow",
        ),
    ]


__all__ = ["OveragePolicy", "PlanCatalog", "PlanDefinition"]
