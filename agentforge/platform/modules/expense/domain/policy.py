"""策略模块。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExpensePolicyEvaluation(BaseModel):
    """报销策略评估相关组件。

    Attributes:
        category_limit_cents: 限制分。
        monthly_budget_cents: 月度预算分。
        committed_cents: 分。
        projected_total_cents: 总计分。
        violations: 字段值。
        requires_approval: 要求审批。
    """

    model_config = ConfigDict(extra="forbid")

    category_limit_cents: int | None = None
    monthly_budget_cents: int = 0
    committed_cents: int = 0
    projected_total_cents: int = 0
    violations: list[str] = Field(default_factory=list)
    requires_approval: bool = False


class ExpensePolicy:
    """报销策略领域组件。"""

    def __init__(
        self,
        *,
        category_limits: dict[str, int] | None = None,
        monthly_budget_cents: int = 0,
    ) -> None:
        """初始化 ExpensePolicy。

        Args:
            category_limits: 输入参数。
            monthly_budget_cents: 月度预算分。
        """
        self.category_limits = {
            name.strip().lower(): amount
            for name, amount in (category_limits or {}).items()
            if name.strip()
        }
        self.monthly_budget_cents = max(0, monthly_budget_cents)

    @classmethod
    def from_config(cls, values: dict[str, object]) -> "ExpensePolicy":
        """从配置构造策略对象。

        Args:
            values: 字段值集合。

        Returns:
            处理结果对象。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        limits = values.get("category_limits", {})
        if isinstance(limits, str):
            limits = _parse_limits(limits)
        if not isinstance(limits, dict):
            raise ValueError("expense category_limits must be an object or string")
        parsed_limits: dict[str, int] = {}
        for category, amount in limits.items():
            if not isinstance(category, str) or not isinstance(amount, int) or amount < 0:
                raise ValueError("expense category limits must be non-negative integer cents")
            parsed_limits[category] = amount
        budget = values.get("monthly_budget_cents", 0)
        if not isinstance(budget, int) or budget < 0:
            raise ValueError("expense monthly_budget_cents must be a non-negative integer")
        return cls(category_limits=parsed_limits, monthly_budget_cents=budget)

    def evaluate(
        self,
        *,
        amount_cents: int,
        category: str,
        committed_cents: int,
    ) -> ExpensePolicyEvaluation:
        """评估输入数据并生成结果。

        Args:
            amount_cents: 金额分。
            category: 输入参数。
            committed_cents: 分。

        Returns:
            报销策略评估结果。
        """
        violations: list[str] = []
        category_limit = self.category_limits.get(category.strip().lower())
        if category_limit is not None and amount_cents > category_limit:
            violations.append("category_limit_exceeded")
        projected = committed_cents + amount_cents
        if self.monthly_budget_cents > 0 and projected > self.monthly_budget_cents:
            violations.append("monthly_budget_exceeded")
        return ExpensePolicyEvaluation(
            category_limit_cents=category_limit,
            monthly_budget_cents=self.monthly_budget_cents,
            committed_cents=committed_cents,
            projected_total_cents=projected,
            violations=violations,
            requires_approval=bool(violations),
        )

    def describe(self) -> dict[str, object]:
        """描述报销策略。

        Returns:
            结构化结果字典。
        """
        return {
            "category_limits": dict(sorted(self.category_limits.items())),
            "monthly_budget_cents": self.monthly_budget_cents,
        }


def _parse_limits(raw: str) -> dict[str, int]:
    """解析请求。

    Args:
        raw: 输入参数。

    Returns:
        结构化结果字典。

    Raises:
        ValueError: 输入值或业务状态不合法时抛出。
    """
    result: dict[str, int] = {}
    for item in raw.split(","):
        if not item.strip():
            continue
        category, separator, amount = item.partition("=")
        if not separator:
            raise ValueError("category_limits must use category=amount format")
        try:
            result[category] = int(amount)
        except ValueError as exc:
            raise ValueError("category limit amounts must be integer cents") from exc
    return result
