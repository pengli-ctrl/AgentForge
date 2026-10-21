"""配置模块。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExpenseModuleConfig(BaseModel):
    """报销模块配置模型。

    Attributes:
        category_limits: 字段值。
        monthly_budget_cents: 月度预算分。
        invoice_enforcement: 发票。
        invoice_block_alert_hours: 发票块告警。
        invoice_override_alert_count: 发票覆盖告警数量。
        invoice_alert_sweep_minutes: 发票告警扫描。
        attachment_download_ttl_seconds: 附件下载。
    """

    model_config = ConfigDict(extra="forbid")

    category_limits: str = ""
    monthly_budget_cents: int = Field(default=0, ge=0)
    invoice_enforcement: str = "off"
    invoice_block_alert_hours: float = Field(default=24.0, ge=0)
    invoice_override_alert_count: int = Field(default=5, ge=0)
    invoice_alert_sweep_minutes: float = Field(default=15.0, ge=0)
    attachment_download_ttl_seconds: int = Field(default=300, ge=1, le=3600)


def default_expense_config() -> ExpenseModuleConfig:
    """创建默认报销配置。

    Returns:
        报销模块配置结果。
    """
    return ExpenseModuleConfig()


__all__ = ["ExpenseModuleConfig", "default_expense_config"]
