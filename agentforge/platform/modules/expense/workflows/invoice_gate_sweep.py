"""发票门禁扫描模块。"""

from __future__ import annotations

from datetime import timedelta
from typing import cast

from temporalio import activity, workflow


@activity.defn
async def sweep_expense_invoice_gate_alerts_activity() -> dict:
    """扫描报销发票门禁告警活动。

    Returns:
        结构化结果字典。
    """
    from agentforge.platform.modules.expense.runtime import get_expense_runtime

    return await get_expense_runtime().invoice_service.scan_all_gate_alerts()


@workflow.defn
class ExpenseInvoiceGateSweepWorkflow:
    """报销发票门禁扫描工作流。"""

    @workflow.run
    async def run(self) -> dict:
        """运行报销发票门禁扫描。

        Returns:
            结构化结果字典。
        """
        return cast(
            dict,
            await workflow.execute_activity(
                sweep_expense_invoice_gate_alerts_activity,
                start_to_close_timeout=timedelta(minutes=30),
            ),
        )
