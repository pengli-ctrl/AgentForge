"""测试Temporal测试模块。"""

from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.worker import Worker

from agentforge.platform.infrastructure.temporal.client import TemporalWorkflowClient
from tests.infra.conftest import RUN_INFRA

pytestmark = [
    pytest.mark.infra,
    pytest.mark.skipif(not RUN_INFRA, reason="set AGENTFORGE_RUN_INFRA_TESTS=1"),
]

_ADDRESS = os.environ.get("AGENTFORGE_TEMPORAL_ADDRESS", "localhost:7233")
_NAMESPACE = os.environ.get("AGENTFORGE_TEMPORAL_NAMESPACE", "default")
_ATTEMPTS: dict[str, int] = {}


@activity.defn
async def retry_probe_activity(payload: dict) -> dict:
    """重试探针活动。

    Args:
        payload: 事件、工作流或请求载荷。

    Returns:
        结构化结果字典。

    Raises:
        RuntimeError: 运行时依赖或状态不满足要求时抛出。
    """
    key = str(payload["key"])
    _ATTEMPTS[key] = _ATTEMPTS.get(key, 0) + 1
    if _ATTEMPTS[key] < int(payload.get("succeed_on_attempt", 1)):
        raise RuntimeError("retry me")
    return {"key": key, "attempts": _ATTEMPTS[key], "task_queue": activity.info().task_queue}


@workflow.defn(sandboxed=False)
class InfrastructureRetryWorkflow:
    """基础设施重试工作流。"""

    @workflow.run
    async def run(self, payload: dict) -> dict:
        """运行基础设施重试。

        Args:
            payload: 事件、工作流或请求载荷。

        Returns:
            结构化结果字典。
        """
        return await workflow.execute_activity(
            retry_probe_activity,
            payload,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(milliseconds=100),
                maximum_attempts=3,
            ),
        )


@pytest.mark.asyncio
async def test_temporal_schedule_worker_retry_and_multiple_queues() -> None:
    """验证Temporal调度工作进程重试及多个队列对应的测试场景。"""
    client = await Client.connect(_ADDRESS, namespace=_NAMESPACE)
    queue_one = f"infra-one-{uuid4()}"
    queue_two = f"infra-two-{uuid4()}"
    worker_one = Worker(
        client,
        task_queue=queue_one,
        workflows=[InfrastructureRetryWorkflow],
        activities=[retry_probe_activity],
    )
    worker_two = Worker(
        client,
        task_queue=queue_two,
        workflows=[InfrastructureRetryWorkflow],
        activities=[retry_probe_activity],
    )
    tasks = [asyncio.create_task(worker_one.run()), asyncio.create_task(worker_two.run())]
    try:
        key_one = f"retry-{uuid4()}"
        key_two = f"multi-{uuid4()}"
        result_one, result_two = await asyncio.gather(
            client.execute_workflow(
                InfrastructureRetryWorkflow.run,
                {"key": key_one, "succeed_on_attempt": 2},
                id=f"wf-{uuid4()}",
                task_queue=queue_one,
            ),
            client.execute_workflow(
                InfrastructureRetryWorkflow.run,
                {"key": key_two, "succeed_on_attempt": 1},
                id=f"wf-{uuid4()}",
                task_queue=queue_two,
            ),
        )
        assert result_one["attempts"] == 2
        assert result_one["task_queue"] == queue_one
        assert result_two["attempts"] == 1
        assert result_two["task_queue"] == queue_two

        schedule_client = TemporalWorkflowClient(_ADDRESS, _NAMESPACE)
        schedule_id = f"infra-schedule-{uuid4()}"
        await schedule_client.ensure_schedule(
            InfrastructureRetryWorkflow,
            {"key": f"schedule-{uuid4()}", "succeed_on_attempt": 1},
            schedule_id=schedule_id,
            interval_seconds=60,
            task_queue=queue_one,
            workflow_id=f"{schedule_id}-run",
        )
        handle = client.get_schedule_handle(schedule_id)
        description = await handle.describe()
        assert description.id == schedule_id
        await handle.delete()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
