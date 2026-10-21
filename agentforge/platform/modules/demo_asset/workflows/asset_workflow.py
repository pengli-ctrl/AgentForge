"""资产工作流模块。"""

from __future__ import annotations

from datetime import timedelta
from typing import cast

from temporalio import activity, workflow


@activity.defn
async def prepare_asset_activity(payload: dict) -> dict:
    """准备资产活动。

    Args:
        payload: 事件、工作流或请求载荷。

    Returns:
        结构化结果字典。
    """
    return {
        "tenant_id": str(payload.get("tenant_id") or ""),
        "asset_id": str(payload.get("asset_id") or ""),
        "prepared": True,
    }


@workflow.defn
class AssetPreparationWorkflow:
    """资产工作流。"""

    @workflow.run
    async def run(self, payload: dict) -> dict:
        """运行资产。

        Args:
            payload: 事件、工作流或请求载荷。

        Returns:
            结构化结果字典。
        """
        return cast(
            dict,
            await workflow.execute_activity(
                prepare_asset_activity,
                payload,
                start_to_close_timeout=timedelta(seconds=30),
            ),
        )


__all__ = ["AssetPreparationWorkflow", "prepare_asset_activity"]
