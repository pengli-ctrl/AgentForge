"""任务模块。"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.api.middleware.error_handler import (
    INVALID_STATE_TRANSITION,
    NOT_FOUND,
    VALIDATION_ERROR,
)
from agentforge.storage.models.task import Task, TaskPriority, TaskStatus
from agentforge.storage.task_store import TaskStore

logger = logging.getLogger(__name__)


class TaskRoutes:
    """任务管理路由处理器。"""

    # 单页允许返回的最大条数，避免超大 limit 拖垮查询。
    MAX_LIMIT = 1000

    def __init__(
        self,
        task_store: TaskStore,
        workflow_engine: Any = None,
    ) -> None:
        """初始化 TaskRoutes。

        Args:
            task_store: 任务存储。
            workflow_engine: 工作流引擎。
        """
        self.task_store = task_store
        self.workflow_engine = workflow_engine

    async def create_task(self, body: dict[str, Any]) -> dict[str, Any]:
        """提交新任务。

        Args:
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            VALIDATION_ERROR: 操作无法完成时抛出。
        """
        workflow_name = body.get("workflow_name", "")
        if not workflow_name:
            raise VALIDATION_ERROR

        input_data = body.get("input_data", {})
        priority_str = body.get("priority", "task_primary")

        try:
            priority = TaskPriority(priority_str)
        except ValueError:
            priority = TaskPriority.TASK_PRIMARY

        task = Task(
            workflow_name=workflow_name,
            input_data=input_data,
            priority=priority,
        )

        await self.task_store.create(task)

        logger.info(
            "Task created via API (task_id=%s, workflow=%s)",
            task.task_id,
            workflow_name,
        )

        # 异步执行任务（如果配置了工作流引擎）
        if self.workflow_engine:
            import asyncio

            asyncio.create_task(self._execute_task(task))

        return task.to_dict()

    async def get_task(self, task_id: str) -> dict[str, Any]:
        """查询任务详情。

        Args:
            task_id: 任务 ID。

        Returns:
            结构化结果字典。

        Raises:
            NOT_FOUND: 操作无法完成时抛出。
        """
        task = await self.task_store.get(task_id)
        if task is None:
            raise NOT_FOUND
        return task.to_dict()

    async def get_task_result(self, task_id: str) -> dict[str, Any]:
        """获取任务结果。

        Args:
            task_id: 任务 ID。

        Returns:
            结构化结果字典。

        Raises:
            NOT_FOUND: 操作无法完成时抛出。
        """
        task = await self.task_store.get(task_id)
        if task is None:
            raise NOT_FOUND

        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "result": task.result,
            "error": task.error,
        }

    async def cancel_task(self, task_id: str) -> dict[str, Any]:
        """取消任务。

        Args:
            task_id: 任务 ID。

        Returns:
            结构化结果字典。

        Raises:
            NOT_FOUND: 操作无法完成时抛出。
            INVALID_STATE_TRANSITION: 操作无法完成时抛出。
        """
        task = await self.task_store.get(task_id)
        if task is None:
            raise NOT_FOUND

        result = await self.task_store.cancel(task_id)
        if result is None:
            raise INVALID_STATE_TRANSITION

        return result.to_dict()

    async def list_tasks(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """查询任务列表。

        Args:
            status: 目标状态。
            limit: 返回记录的最大数量。
            offset: 分页偏移量。

        Returns:
            结构化结果字典。

        Raises:
            VALIDATION_ERROR: 操作无法完成时抛出。
        """
        # 边界校验：拒绝负值并对 limit 设上限，避免 LIMIT -1 / 超大 limit 问题。
        limit = max(0, min(int(limit), self.MAX_LIMIT))
        offset = max(0, int(offset))

        task_status = None
        if status:
            try:
                task_status = TaskStatus(status)
            except ValueError:
                raise VALIDATION_ERROR

        tasks = await self.task_store.list_tasks(status=task_status, limit=limit, offset=offset)

        return {
            "tasks": [t.to_dict() for t in tasks],
            "returned": len(tasks),
            "limit": limit,
            "offset": offset,
        }

    async def _execute_task(self, task: Task) -> None:
        """异步执行任务（内部方法）。

        Args:
            task: 任务对象。
        """
        try:
            await self.task_store.update_status(task.task_id, TaskStatus.RUNNING)

            result = await self.workflow_engine.execute(
                task.workflow_name,
                task.correlation_id,
                task.input_data,
            )

            await self.task_store.update_status(
                task.task_id,
                TaskStatus.COMPLETED,
                result=result,
            )
        except Exception as e:
            logger.error(
                "Task execution failed (task_id=%s, error=%s)",
                task.task_id,
                e,
                exc_info=True,
            )
            await self.task_store.update_status(
                task.task_id,
                TaskStatus.FAILED,
                error=str(e),
            )
