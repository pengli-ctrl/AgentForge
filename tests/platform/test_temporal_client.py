import pytest

from agentforge.platform.infrastructure.temporal.client import TemporalWorkflowClient


class FakeWorkflowHandle:
    def __init__(self) -> None:
        self.signals: list[tuple[str, dict]] = []

    async def signal(self, name: str, payload: dict) -> None:
        self.signals.append((name, payload))


class FakeTemporalClient:
    def __init__(self) -> None:
        self.started: list[dict] = []
        self.handles: dict[str, FakeWorkflowHandle] = {}

    async def start_workflow(self, workflow, event, id, task_queue):
        self.started.append({"event": event, "id": id, "task_queue": task_queue})

    def get_workflow_handle(self, workflow_id: str) -> FakeWorkflowHandle:
        handle = self.handles.setdefault(workflow_id, FakeWorkflowHandle())
        return handle


@pytest.mark.asyncio
async def test_temporal_client_starts_and_signals_workflow() -> None:
    fake = FakeTemporalClient()

    async def factory(address, namespace):
        return fake

    client = TemporalWorkflowClient(
        address="temporal:7233",
        namespace="default",
        task_queue="queue-1",
        client_factory=factory,
    )
    workflow_id = await client.start_support_workflow({"tenant_id": "tenant-1"}, workflow_id="wf-1")
    await client.signal_approval("wf-1", "approve", "supervisor-1")
    assert workflow_id == "wf-1"
    assert fake.started[0]["task_queue"] == "queue-1"
    assert fake.handles["wf-1"].signals[0][1]["decision"] == "approve"
