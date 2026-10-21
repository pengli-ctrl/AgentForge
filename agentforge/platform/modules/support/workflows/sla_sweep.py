"""SLA扫描模块。"""

from __future__ import annotations

from datetime import timedelta
from typing import cast

from temporalio import activity, workflow


@activity.defn
async def sweep_support_sla_activity() -> dict:
    """扫描客服SLA活动。

    Returns:
        结构化结果字典。
    """
    from agentforge.platform.modules.support.runtime import get_support_runtime

    return await get_support_runtime().ticket_service.sweep_sla()


@workflow.defn
class SupportSlaSweepWorkflow:
    """客服SLA扫描工作流。"""

    @workflow.run
    async def run(self) -> dict:
        """运行客服SLA扫描。

        Returns:
            结构化结果字典。
        """
        return cast(
            dict,
            await workflow.execute_activity(
                sweep_support_sla_activity,
                start_to_close_timeout=timedelta(minutes=30),
            ),
        )
