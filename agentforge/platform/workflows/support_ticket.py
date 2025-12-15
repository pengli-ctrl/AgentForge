from __future__ import annotations

from datetime import timedelta

from temporalio import activity, workflow

from agentforge.platform.runtime import get_container


@activity.defn
async def intake_ticket_activity(event: dict) -> dict:
    ticket = await get_container().processing_service.process_event(event)
    return ticket.model_dump(mode="json")


@activity.defn
async def apply_approval_activity(
    tenant_id: str,
    ticket_id: str,
    decision: str,
    decided_by: str,
) -> dict:
    ticket = await get_container().ticket_service.apply_approval(
        tenant_id=tenant_id,
        ticket_id=ticket_id,
        decision=decision,
        decided_by=decided_by,
    )
    return ticket.model_dump(mode="json")


@workflow.defn
class SupportTicketWorkflow:
    def __init__(self) -> None:
        self._approval_decision: dict | None = None

    @workflow.signal
    async def approve(self, decision: dict) -> None:
        self._approval_decision = decision

    @workflow.query
    def review_state(self) -> dict:
        return {"approval_decision": self._approval_decision}

    @workflow.run
    async def run(self, event: dict) -> dict:
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
