"""客户端模块。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from datetime import timedelta
from typing import Any
from uuid import uuid4

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleIntervalSpec,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
)

from agentforge.platform.domain.usage import UsageMetric
from agentforge.platform.sdk.ports import UsagePort


class TemporalWorkflowClient:
    """Temporal相关组件。"""

    def __init__(
        self,
        address: str,
        namespace: str,
        task_queue: str = "support-copilot",
        client_factory: Callable[..., Awaitable[Client]] | None = None,
    ) -> None:
        """初始化 TemporalWorkflowClient。

        Args:
            address: 输入参数。
            namespace: 输入参数。
            task_queue: 任务队列。
            client_factory: 客户端工厂。
        """
        self._address = address
        self._namespace = namespace
        self._task_queue = task_queue
        self._client_factory = client_factory or Client.connect
        self._client: Client | None = None
        self._usage_meter: UsagePort | None = None

    def set_usage_meter(self, usage_meter: UsagePort) -> None:
        """设置用量计量。

        Args:
            usage_meter: 用量计量。
        """
        self._usage_meter = usage_meter

    async def _get_client(self) -> Client:
        """获取客户端。

        Returns:
            客户端结果。
        """
        if self._client is None:
            self._client = await self._client_factory(
                self._address,
                namespace=self._namespace,
            )
        return self._client

    async def start_workflow(
        self,
        workflow: Any,
        arg: Any,
        *,
        workflow_id: str | None = None,
        id_prefix: str = "workflow",
        task_queue: str | None = None,
    ) -> str:
        """执行开始工作流。

        Args:
            workflow: 工作流定义或实例。
            arg: 输入参数。
            workflow_id: 工作流 ID。
            id_prefix: ID前缀。
            task_queue: 任务队列。

        Returns:
            字符串结果。
        """
        client = await self._get_client()
        resolved_id = workflow_id or f"{id_prefix}-{uuid4()}"
        await client.start_workflow(
            workflow,
            arg,
            id=resolved_id,
            task_queue=task_queue or self._task_queue,
        )
        tenant_id = ""
        if isinstance(arg, Mapping):
            tenant_id = str(arg.get("tenant_id") or "").strip()
        else:
            tenant_id = str(getattr(arg, "tenant_id", "") or "").strip()
        if self._usage_meter is not None and tenant_id:
            await self._usage_meter.record(
                tenant_id=tenant_id,
                metric=UsageMetric.WORKFLOW_EXECUTIONS,
                quantity=1,
                source="temporal",
                idempotency_key=f"workflow:{resolved_id}",
                metadata={"workflow_id": resolved_id},
            )
        return resolved_id

    async def signal_workflow(
        self,
        workflow_id: str,
        signal: Any,
        arg: Any = None,
    ) -> None:
        """通知工作流。

        Args:
            workflow_id: 工作流 ID。
            signal: 信号。
            arg: 输入参数。
        """
        client = await self._get_client()
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal(signal, arg)

    async def ensure_schedule(
        self,
        workflow: Any,
        arg: Any,
        *,
        schedule_id: str,
        interval_seconds: float,
        task_queue: str | None = None,
        workflow_id: str | None = None,
    ) -> str:
        """确保调度。

        Args:
            workflow: 工作流定义或实例。
            arg: 输入参数。
            schedule_id: 调度 ID。
            interval_seconds: 输入参数。
            task_queue: 任务队列。
            workflow_id: 工作流 ID。

        Returns:
            字符串结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        client = await self._get_client()
        interval = timedelta(seconds=interval_seconds)
        schedule = Schedule(
            action=ScheduleActionStartWorkflow(
                workflow,
                arg,
                id=workflow_id or f"{schedule_id}-run",
                task_queue=task_queue or self._task_queue,
                static_summary=schedule_id,
            ),
            spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=interval)]),
            policy=SchedulePolicy(
                overlap=ScheduleOverlapPolicy.SKIP,
                catchup_window=interval,
            ),
        )
        try:
            await client.create_schedule(schedule_id, schedule)
        except ScheduleAlreadyRunningError:
            return schedule_id
        return schedule_id
