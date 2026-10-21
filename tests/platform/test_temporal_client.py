"""Temporal客户端测试模块。

本测试模块验证 test_temporal_client 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：FakeWorkflowHandle、FakeTemporalClient。
- 主要函数：test_temporal_client_starts_and_signals_workflow。
"""

from datetime import timedelta

import pytest

from agentforge.platform.infrastructure.temporal.client import TemporalWorkflowClient
from agentforge.platform.modules.expense.workflows.invoice_gate_sweep import (
    ExpenseInvoiceGateSweepWorkflow,
)


class FakeWorkflowHandle:
    """用于测试的模拟处理。"""

    def __init__(self) -> None:
        """初始化模拟处理。"""
        self.signals: list[tuple[str, dict]] = []

    async def signal(self, name: str, payload: dict) -> None:
        """发送信号模拟处理。

        Args:
            name: 资源或对象名称。
            payload: 事件、工作流或请求载荷。
        """
        self.signals.append((name, payload))


class FakeTemporalClient:
    """用于测试的模拟Temporal。"""

    def __init__(self) -> None:
        """初始化模拟Temporal。"""
        self.started: list[dict] = []
        self.handles: dict[str, FakeWorkflowHandle] = {}
        self.schedules: dict[str, object] = {}

    async def start_workflow(self, workflow, event, id, task_queue):
        """启动工作流。

        Args:
            workflow: 工作流定义或实例。
            event: 待处理事件。
            id: ID。
            task_queue: 任务队列。
        """
        self.started.append({"event": event, "id": id, "task_queue": task_queue})

    async def create_schedule(self, schedule_id: str, schedule: object) -> None:
        """创建调度。

        Args:
            schedule_id: 调度 ID。
            schedule: 调度。
        """
        self.schedules[schedule_id] = schedule

    def get_workflow_handle(self, workflow_id: str) -> FakeWorkflowHandle:
        """获取工作流处理。

        Args:
            workflow_id: 工作流 ID。

        Returns:
            模拟工作流处理结果。
        """
        handle = self.handles.setdefault(workflow_id, FakeWorkflowHandle())
        return handle


@pytest.mark.asyncio
async def test_temporal_client_starts_and_signals_workflow() -> None:
    """验证Temporal客户端开始及工作流对应的测试场景。"""
    fake = FakeTemporalClient()

    async def factory(address, namespace):
        """处理工厂。

        Args:
            address: 输入参数。
            namespace: 输入参数。

        Returns:
            处理结果。
        """
        return fake

    client = TemporalWorkflowClient(
        address="temporal:7233",
        namespace="default",
        task_queue="queue-1",
        client_factory=factory,
    )

    async def workflow_run(event):
        """处理工作流运行。

        Args:
            event: 待处理事件。

        Returns:
            处理结果。
        """
        return event

    async def workflow_approve(payload):
        """处理工作流批准。

        Args:
            payload: 事件、工作流或请求载荷。

        Returns:
            处理结果。
        """
        return payload

    workflow_id = await client.start_workflow(
        workflow_run,
        {"tenant_id": "tenant-1"},
        workflow_id="wf-1",
    )
    await client.signal_workflow(
        "wf-1",
        workflow_approve,
        {"decision": "approve", "decided_by": "supervisor-1"},
    )
    assert workflow_id == "wf-1"
    assert fake.started[0]["task_queue"] == "queue-1"
    assert fake.handles["wf-1"].signals[0][1]["decision"] == "approve"


@pytest.mark.asyncio
async def test_temporal_client_creates_skipping_interval_schedule() -> None:
    """验证Temporal客户端创建调度对应的测试场景。"""
    fake = FakeTemporalClient()

    async def factory(address, namespace):
        """处理工厂。

        Args:
            address: 输入参数。
            namespace: 输入参数。

        Returns:
            处理结果。
        """
        return fake

    client = TemporalWorkflowClient(
        address="temporal:7233",
        namespace="default",
        task_queue="expense-copilot",
        client_factory=factory,
    )

    schedule_id = await client.ensure_schedule(
        ExpenseInvoiceGateSweepWorkflow,
        {},
        schedule_id="expense-invoice-gate-sweep",
        interval_seconds=900,
        workflow_id="expense-invoice-gate-sweep-run",
    )

    schedule = fake.schedules[schedule_id]
    assert schedule.spec.intervals[0].every == timedelta(minutes=15)
    assert schedule.action.task_queue == "expense-copilot"
    assert schedule.action.id == "expense-invoice-gate-sweep-run"
