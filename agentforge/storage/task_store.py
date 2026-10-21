"""任务存储模块。"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.storage.models.task import Task, TaskPriority, TaskStatus

logger = logging.getLogger(__name__)


class TaskStore:
    """任务领域组件。"""

    def __init__(self, db_pool: Any = None) -> None:
        """初始化 TaskStore。

        Args:
            db_pool: 数据库。
        """
        self.db_pool = db_pool
        self._store: dict[str, Task] = {}

    async def create(self, task: Task) -> Task:
        """创建新任务。

        Args:
            task: 任务对象。

        Returns:
            任务结果。
        """
        if self.db_pool:
            await self._db_create(task)
        else:
            self._store[task.task_id] = task

        logger.info(
            "Task created (task_id=%s, workflow=%s, correlation_id=%s)",
            task.task_id,
            task.workflow_name,
            task.correlation_id,
        )
        return task

    async def get(self, task_id: str) -> Task | None:
        """根据任务 ID 查询任务。

        Args:
            task_id: 任务 ID。

        Returns:
            任务无结果。
        """
        if self.db_pool:
            return await self._db_get(task_id)
        return self._store.get(task_id)

    async def get_by_correlation_id(self, correlation_id: str) -> Task | None:
        """获取由关联ID。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。

        Returns:
            任务无结果。
        """
        if self.db_pool:
            return await self._db_get_by_correlation_id(correlation_id)

        for task in self._store.values():
            if task.correlation_id == correlation_id:
                return task
        return None

    async def update_status(
        self,
        task_id: str,
        new_status: TaskStatus,
        result: dict[str, Any] | None = None,
        error: str = "",
    ) -> Task | None:
        """更新任务状态（带状态机校验）。

        Args:
            task_id: 任务 ID。
            new_status: 状态。
            result: 处理结果。
            error: 错误。

        Returns:
            任务无结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        task = await self.get(task_id)
        if task is None:
            return None

        if not Task.can_transition(task.status, new_status):
            raise ValueError(f"Invalid status transition: {task.status.value} → {new_status.value}")

        task.status = new_status
        if new_status == TaskStatus.RUNNING:
            task.started_at = task.started_at or __import__("time").time()
        if new_status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            task.completed_at = __import__("time").time()
        if result is not None:
            task.result = result
        if error:
            task.error = error

        if self.db_pool:
            await self._db_update(task)
        else:
            self._store[task_id] = task

        logger.info(
            "Task status updated (task_id=%s, status=%s)",
            task_id,
            new_status.value,
        )
        return task

    async def cancel(self, task_id: str) -> Task | None:
        """取消任务。

        Args:
            task_id: 任务 ID。

        Returns:
            任务无结果。
        """
        task = await self.get(task_id)
        if task is None:
            return None

        if not Task.can_transition(task.status, TaskStatus.CANCELLED):
            logger.warning(
                "Cannot cancel task in %s state (task_id=%s)",
                task.status.value,
                task_id,
            )
            return None

        return await self.update_status(task_id, TaskStatus.CANCELLED)

    async def list_tasks(
        self,
        status: TaskStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        """查询任务列表。

        Args:
            status: 目标状态。
            limit: 返回记录的最大数量。
            offset: 分页偏移量。

        Returns:
            结果列表。
        """
        if self.db_pool:
            return await self._db_list(status, limit, offset)

        tasks = list(self._store.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks[offset : offset + limit]

    async def delete(self, task_id: str) -> bool:
        """删除任务。

        Args:
            task_id: 任务 ID。

        Returns:
            操作是否成功。
        """
        if self.db_pool:
            return await self._db_delete(task_id)

        if task_id in self._store:
            del self._store[task_id]
            return True
        return False

    # --- MySQL 后端方法（生产环境使用） ---

    async def _db_create(self, task: Task) -> None:
        """处理数据库创建。

        Args:
            task: 任务对象。
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO tasks (task_id, workflow_name, input_data, status, "
                "priority, correlation_id, result, error, created_at, "
                "started_at, completed_at, metadata) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    task.task_id,
                    task.workflow_name,
                    _json_dumps(task.input_data),
                    task.status.value,
                    task.priority.value,
                    task.correlation_id,
                    _json_dumps(task.result),
                    task.error,
                    task.created_at,
                    task.started_at,
                    task.completed_at,
                    _json_dumps(task.metadata),
                ),
            )

    async def _db_get(self, task_id: str) -> Task | None:
        """处理数据库获取。

        Args:
            task_id: 任务 ID。

        Returns:
            任务无结果。
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchone("SELECT * FROM tasks WHERE task_id = %s", (task_id,))
            return _row_to_task(row) if row else None

    async def _db_get_by_correlation_id(self, correlation_id: str) -> Task | None:
        """处理数据库获取由关联ID。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。

        Returns:
            任务无结果。
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchone(
                "SELECT * FROM tasks WHERE correlation_id = %s",
                (correlation_id,),
            )
            return _row_to_task(row) if row else None

    async def _db_update(self, task: Task) -> None:
        """处理数据库更新。

        Args:
            task: 任务对象。
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE tasks SET status=%s, result=%s, error=%s, "
                "started_at=%s, completed_at=%s WHERE task_id=%s",
                (
                    task.status.value,
                    _json_dumps(task.result),
                    task.error,
                    task.started_at,
                    task.completed_at,
                    task.task_id,
                ),
            )

    async def _db_list(self, status: TaskStatus | None, limit: int, offset: int) -> list[Task]:
        """处理数据库查询。

        Args:
            status: 目标状态。
            limit: 返回记录的最大数量。
            offset: 分页偏移量。

        Returns:
            结果列表。
        """
        async with self.db_pool.acquire() as conn:
            if status is not None:
                rows = await conn.fetchall(
                    "SELECT * FROM tasks WHERE status=%s "
                    "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    (status.value, limit, offset),
                )
            else:
                rows = await conn.fetchall(
                    "SELECT * FROM tasks ORDER BY created_at DESC " "LIMIT %s OFFSET %s",
                    (limit, offset),
                )
            return [_row_to_task(row) for row in rows]

    async def _db_delete(self, task_id: str) -> bool:
        """判断数据库删除是否成立。

        Args:
            task_id: 任务 ID。

        Returns:
            操作是否成功。
        """
        async with self.db_pool.acquire() as conn:
            result = await conn.execute("DELETE FROM tasks WHERE task_id = %s", (task_id,))
            return result > 0


def _json_dumps(data: Any) -> str:
    """处理JSON。

    Args:
        data: 待处理数据。

    Returns:
        字符串结果。
    """
    import json

    return json.dumps(data, ensure_ascii=False, default=str)


def _row_to_task(row: Any) -> Task:
    """处理记录到任务。

    Args:
        row: 记录。

    Returns:
        任务结果。
    """
    import json

    if isinstance(row, dict):
        data = dict(row)
    else:
        # 假设是 namedtuple 或类似结构
        data = dict(row._asdict()) if hasattr(row, "_asdict") else {}

    input_data = data.get("input_data", "{}")
    if isinstance(input_data, str):
        input_data = json.loads(input_data) if input_data else {}

    result = data.get("result", "{}")
    if isinstance(result, str):
        result = json.loads(result) if result else {}

    metadata = data.get("metadata", "{}")
    if isinstance(metadata, str):
        metadata = json.loads(metadata) if metadata else {}

    return Task(
        task_id=data.get("task_id", ""),
        workflow_name=data.get("workflow_name", ""),
        input_data=input_data,
        status=TaskStatus(data.get("status", "pending")),
        priority=TaskPriority(data.get("priority", "task_primary")),
        correlation_id=data.get("correlation_id", ""),
        result=result,
        error=data.get("error", ""),
        created_at=data.get("created_at", 0.0),
        started_at=data.get("started_at", 0.0),
        completed_at=data.get("completed_at", 0.0),
        metadata=metadata,
    )
