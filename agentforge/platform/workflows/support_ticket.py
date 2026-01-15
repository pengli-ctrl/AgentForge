"""AgentForge 平台工作流层：support_ticket。

本模块负责 support_ticket 相关的平台能力，是 平台工作流层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：SupportTicketWorkflow。
- 主要函数：intake_ticket_activity、apply_approval_activity。
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import activity, workflow


@activity.defn
async def intake_ticket_activity(event: dict) -> dict:
    """执行 intake_ticket_activity 对应的逻辑，并返回处理结果。

    Args:
        event: dict，调用方传入的 event 参数。

    Returns:
        dict，函数执行后的结果。
    """
    from agentforge.platform.runtime import get_container

    ticket = await get_container().processing_service.process_event(event)
    return ticket.model_dump(mode="json")


@activity.defn
async def apply_approval_activity(
    tenant_id: str,
    ticket_id: str,
    decision: str,
    decided_by: str,
) -> dict:
    """应用业务变更，并返回调用方需要的结果。

    Args:
        tenant_id: str，调用方传入的 tenant_id 参数。
        ticket_id: str，调用方传入的 ticket_id 参数。
        decision: str，调用方传入的 decision 参数。
        decided_by: str，调用方传入的 decided_by 参数。

    Returns:
        dict，函数执行后的结果。
    """
    from agentforge.platform.runtime import get_container

    ticket = await get_container().ticket_service.apply_approval(
        tenant_id=tenant_id,
        ticket_id=ticket_id,
        decision=decision,
        decided_by=decided_by,
    )
    return ticket.model_dump(mode="json")


@workflow.defn
class SupportTicketWorkflow:
    """SupportTicketWorkflow。

    SupportTicketWorkflow 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 approve()。
    - 方法 review_state()。
    - 方法 run()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._approval_decision: dict | None = None

    @workflow.signal
    async def approve(self, decision: dict) -> None:
        """执行 approve 对应的逻辑，并返回处理结果。

        Args:
            decision: dict，调用方传入的 decision 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._approval_decision = decision

    @workflow.query
    def review_state(self) -> dict:
        """执行 review_state 对应的逻辑，并返回处理结果。

        Returns:
            dict，函数执行后的结果。
        """
        return {"approval_decision": self._approval_decision}

    @workflow.run
    async def run(self, event: dict) -> dict:
        """执行 run 对应的逻辑，并返回处理结果。

        Args:
            event: dict，调用方传入的 event 参数。

        Returns:
            dict，函数执行后的结果。
        """
        ticket = await workflow.execute_activity(
            intake_ticket_activity,
            event,
            start_to_close_timeout=timedelta(seconds=30),
        )
        if ticket["status"] != "waiting_approval":
            return ticket

        await workflow.wait_condition(lambda: self._approval_decision is not None)
        decision = self._approval_decision or {}
        return await workflow.execute_activity(
            apply_approval_activity,
            args=[
                ticket["tenant_id"],
                ticket["ticket_id"],
                decision.get("decision", "reject"),
                decision.get("decided_by", "unknown"),
            ],
            start_to_close_timeout=timedelta(seconds=30),
        )
