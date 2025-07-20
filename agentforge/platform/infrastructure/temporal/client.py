from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import uuid4

from temporalio.client import Client

from agentforge.platform.workflows.support_ticket import SupportTicketWorkflow


class TemporalWorkflowClient:
    def __init__(
        self,
        address: str,
        namespace: str,
        task_queue: str = "support-copilot",
        client_factory: Callable[..., Awaitable[Client]] | None = None,
    ) -> None:
        self._address = address
        self._namespace = namespace
        self._task_queue = task_queue
        self._client_factory = client_factory or Client.connect
        self._client: Client | None = None

    async def _get_client(self) -> Client:
        if self._client is None:
            self._client = await self._client_factory(
                self._address,
                namespace=self._namespace,
            )
        return self._client

    async def start_support_workflow(self, event: dict, workflow_id: str | None = None) -> str:
        client = await self._get_client()
        resolved_id = workflow_id or f"support-{uuid4()}"
        await client.start_workflow(
            SupportTicketWorkflow.run,
            event,
            id=resolved_id,
            task_queue=self._task_queue,
        )
        return resolved_id

    async def signal_approval(
        self,
        workflow_id: str,
        decision: str,
        decided_by: str,
    ) -> None:
        client = await self._get_client()
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal(
            SupportTicketWorkflow.approve,
            {"decision": decision, "decided_by": decided_by},
        )
