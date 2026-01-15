"""AgentForge 平台测试层：test_temporal_client。

本测试模块验证 test_temporal_client 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：FakeWorkflowHandle、FakeTemporalClient。
- 主要函数：test_temporal_client_starts_and_signals_workflow。
"""

import pytest

from agentforge.platform.infrastructure.temporal.client import TemporalWorkflowClient


class FakeWorkflowHandle:
    """FakeWorkflowHandle。

    FakeWorkflowHandle 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 signal()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self.signals: list[tuple[str, dict]] = []

    async def signal(self, name: str, payload: dict) -> None:
        """执行 signal 对应的逻辑，并返回处理结果。

        Args:
            name: str，调用方传入的 name 参数。
            payload: dict，调用方传入的 payload 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.signals.append((name, payload))


class FakeTemporalClient:
    """FakeTemporalClient。

    FakeTemporalClient 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

    主要成员：
    - 方法 start_workflow()。
    - 方法 get_workflow_handle()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self.started: list[dict] = []
        self.handles: dict[str, FakeWorkflowHandle] = {}

    async def start_workflow(self, workflow, event, id, task_queue):
        """执行 start_workflow 对应的逻辑，并返回处理结果。

        Args:
            workflow: Any，调用方传入的 workflow 参数。
            event: Any，调用方传入的 event 参数。
            id: Any，调用方传入的 id 参数。
            task_queue: Any，调用方传入的 task_queue 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.started.append({"event": event, "id": id, "task_queue": task_queue})

    def get_workflow_handle(self, workflow_id: str) -> FakeWorkflowHandle:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            workflow_id: str，调用方传入的 workflow_id 参数。

        Returns:
            FakeWorkflowHandle，函数执行后的结果。
        """
        handle = self.handles.setdefault(workflow_id, FakeWorkflowHandle())
        return handle


@pytest.mark.asyncio
async def test_temporal_client_starts_and_signals_workflow() -> None:
    """验证 temporal_client_starts_and_signals_workflow 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    fake = FakeTemporalClient()

    async def factory(address, namespace):
        """执行 factory 对应的逻辑，并返回处理结果。

        Args:
            address: Any，调用方传入的 address 参数。
            namespace: Any，调用方传入的 namespace 参数。

        Returns:
            None，函数执行后的结果。
        """
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
