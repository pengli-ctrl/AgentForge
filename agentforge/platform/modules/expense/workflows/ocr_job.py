"""OCR任务模块。"""

from __future__ import annotations

from datetime import timedelta
from typing import cast

from temporalio import activity, workflow


@activity.defn
async def process_expense_ocr_job_activity(payload: dict) -> dict:
    """处理报销OCR任务活动。

    Args:
        payload: 事件、工作流或请求载荷。

    Returns:
        结构化结果字典。
    """
    from agentforge.platform.modules.expense.runtime import get_expense_runtime

    job = await get_expense_runtime().ocr_job_service.process(
        str(payload["tenant_id"]),
        str(payload["job_id"]),
    )
    return job.model_dump(mode="json")


@workflow.defn
class ExpenseOcrWorkflow:
    """报销OCR的 Temporal 工作流。"""

    @workflow.run
    async def run(self, payload: dict) -> dict:
        """运行报销OCR。

        Args:
            payload: 事件、工作流或请求载荷。

        Returns:
            结构化结果字典。
        """
        return cast(
            dict,
            await workflow.execute_activity(
                process_expense_ocr_job_activity,
                payload,
                start_to_close_timeout=timedelta(minutes=5),
            ),
        )
