"""客服工单模块。"""

from __future__ import annotations

from datetime import timedelta
from typing import cast

from temporalio import activity, workflow


@activity.defn
async def intake_ticket_activity(event: dict) -> dict:
    """接收工单活动。

    Args:
        event: 待处理事件。

    Returns:
        结构化结果字典。
    """
    from agentforge.platform.modules.support.runtime import get_support_runtime

    ticket = await get_support_runtime().processing_service.process_event(event)
    return ticket.model_dump(mode="json")


@activity.defn
async def apply_approval_activity(
    tenant_id: str,
    ticket_id: str,
    decision: str,
    decided_by: str,
) -> dict:
    """应用审批活动。

    Args:
        tenant_id: 租户 ID，用于数据隔离。
        ticket_id: 工单 ID。
        decision: 待处理的授权或审批决策。
        decided_by: 由。

    Returns:
        结构化结果字典。
    """
    from agentforge.platform.modules.support.runtime import get_support_runtime

    ticket = await get_support_runtime().ticket_service.apply_approval(
        tenant_id=tenant_id,
        ticket_id=ticket_id,
        decision=decision,
        decided_by=decided_by,
    )
    return ticket.model_dump(mode="json")


@workflow.defn
class SupportTicketWorkflow:
    """客服工单的 Temporal 工作流。"""

    def __init__(self) -> None:
        """初始化 SupportTicketWorkflow。"""
        self._approval_decision: dict | None = None

    @workflow.signal
    async def approve(self, decision: dict) -> None:
        """批准客服工单。

        Args:
            decision: 待处理的授权或审批决策。
        """
        self._approval_decision = decision

    @workflow.query
    def review_state(self) -> dict:
        """审核状态。

        Returns:
            结构化结果字典。
        """
        return {"approval_decision": self._approval_decision}

    @workflow.run
    async def run(self, event: dict) -> dict:
        """运行客服工单。

        Args:
            event: 待处理事件。

        Returns:
            结构化结果字典。
        """
        ticket = cast(
            dict[str, object],
            await workflow.execute_activity(
                intake_ticket_activity,
                event,
                start_to_close_timeout=timedelta(seconds=30),
            ),
        )
        if ticket["status"] != "waiting_approval":
            return ticket

        await workflow.wait_condition(lambda: self._approval_decision is not None)
        decision = self._approval_decision or {}
        result = await workflow.execute_activity(
            apply_approval_activity,
            args=[
                ticket["tenant_id"],
                ticket["ticket_id"],
                decision.get("decision", "reject"),
                decision.get("decided_by", "unknown"),
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )
        return cast(dict[str, object], result)
