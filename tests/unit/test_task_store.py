"""TaskStore 单元测试 — CRUD 操作与状态机转换。

测试要点：CRUD操作、状态机转换、分页查询。
"""

from __future__ import annotations

import pytest

from agentforge.storage.models.task import Task, TaskStatus
from agentforge.storage.task_store import TaskStore


@pytest.fixture
def store() -> TaskStore:
    """执行 store 对应的逻辑，并返回处理结果。

    Returns:
        TaskStore，函数执行后的结果。
    """
    return TaskStore()


def _make_task(workflow: str = "code-review-pipeline") -> Task:
    """执行 _make_task 对应的逻辑，并返回处理结果。

    Args:
        workflow: str，调用方传入的 workflow 参数。

    Returns:
        Task，函数执行后的结果。
    """
    return Task(
        workflow_name=workflow,
        input_data={"code_content": "print('hello')"},
        correlation_id="corr-test-001",
    )


class TestCreate:
    """创建任务测试。"""

    @pytest.mark.asyncio
    async def test_create_returns_task(self, store: TaskStore) -> None:
        """验证 create_returns_task 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        task = _make_task()
        result = await store.create(task)
        assert result.task_id == task.task_id
        assert result.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_stores_task(self, store: TaskStore) -> None:
        """验证 create_stores_task 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        task = _make_task()
        await store.create(task)
        retrieved = await store.get(task.task_id)
        assert retrieved is not None
        assert retrieved.workflow_name == "code-review-pipeline"


class TestGet:
    """查询任务测试。"""

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, store: TaskStore) -> None:
        """验证 get_nonexistent_returns_none 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        result = await store.get("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_correlation_id(self, store: TaskStore) -> None:
        """验证 get_by_correlation_id 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        task = _make_task()
        await store.create(task)
        result = await store.get_by_correlation_id("corr-test-001")
        assert result is not None
        assert result.task_id == task.task_id

    @pytest.mark.asyncio
    async def test_get_by_correlation_id_not_found(self, store: TaskStore) -> None:
        """验证 get_by_correlation_id_not_found 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        result = await store.get_by_correlation_id("no-such-corr")
        assert result is None


class TestStatusTransition:
    """状态机转换测试。"""

    @pytest.mark.asyncio
    async def test_pending_to_running(self, store: TaskStore) -> None:
        """验证 pending_to_running 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        task = _make_task()
        await store.create(task)
        updated = await store.update_status(task.task_id, TaskStatus.RUNNING)
        assert updated is not None
        assert updated.status == TaskStatus.RUNNING
        assert updated.started_at > 0

    @pytest.mark.asyncio
    async def test_running_to_completed(self, store: TaskStore) -> None:
        """验证 running_to_completed 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        task = _make_task()
        await store.create(task)
        await store.update_status(task.task_id, TaskStatus.RUNNING)
        updated = await store.update_status(
            task.task_id, TaskStatus.COMPLETED, result={"score": 95}
        )
        assert updated.status == TaskStatus.COMPLETED
        assert updated.completed_at > 0
        assert updated.result["score"] == 95

    @pytest.mark.asyncio
    async def test_running_to_failed(self, store: TaskStore) -> None:
        """验证 running_to_failed 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        task = _make_task()
        await store.create(task)
        await store.update_status(task.task_id, TaskStatus.RUNNING)
        updated = await store.update_status(task.task_id, TaskStatus.FAILED, error="timeout")
        assert updated.status == TaskStatus.FAILED
        assert updated.error == "timeout"

    @pytest.mark.asyncio
    async def test_invalid_transition_raises(self, store: TaskStore) -> None:
        """验证 invalid_transition_raises 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        task = _make_task()
        await store.create(task)
        with pytest.raises(ValueError, match="Invalid status transition"):
            await store.update_status(task.task_id, TaskStatus.COMPLETED)

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_none(self, store: TaskStore) -> None:
        """验证 update_nonexistent_returns_none 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        result = await store.update_status("no-such-id", TaskStatus.RUNNING)
        assert result is None


class TestCancel:
    """取消任务测试。"""

    @pytest.mark.asyncio
    async def test_cancel_pending_task(self, store: TaskStore) -> None:
        """验证 cancel_pending_task 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        task = _make_task()
        await store.create(task)
        cancelled = await store.cancel(task.task_id)
        assert cancelled is not None
        assert cancelled.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_completed_task_returns_none(self, store: TaskStore) -> None:
        """验证 cancel_completed_task_returns_none 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        task = _make_task()
        await store.create(task)
        await store.update_status(task.task_id, TaskStatus.RUNNING)
        await store.update_status(task.task_id, TaskStatus.COMPLETED)
        result = await store.cancel(task.task_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, store: TaskStore) -> None:
        """验证 cancel_nonexistent 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        result = await store.cancel("nonexistent")
        assert result is None


class TestListAndDelete:
    """列表和删除测试。"""

    @pytest.mark.asyncio
    async def test_list_all_tasks(self, store: TaskStore) -> None:
        """验证 list_all_tasks 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        for i in range(3):
            await store.create(_make_task(f"wf-{i}"))
        tasks = await store.list_tasks()
        assert len(tasks) == 3

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self, store: TaskStore) -> None:
        """验证 list_filter_by_status 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        t1 = _make_task()
        t2 = _make_task()
        await store.create(t1)
        await store.create(t2)
        await store.update_status(t2.task_id, TaskStatus.RUNNING)
        pending = await store.list_tasks(status=TaskStatus.PENDING)
        assert len(pending) == 1
        running = await store.list_tasks(status=TaskStatus.RUNNING)
        assert len(running) == 1

    @pytest.mark.asyncio
    async def test_delete_task(self, store: TaskStore) -> None:
        """验证 delete_task 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        task = _make_task()
        await store.create(task)
        deleted = await store.delete(task.task_id)
        assert deleted is True
        assert await store.get(task.task_id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, store: TaskStore) -> None:
        """验证 delete_nonexistent 对应的业务行为、边界条件和回归场景。

        Args:
            store: TaskStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        result = await store.delete("nonexistent")
        assert result is False
