"""任务模块。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    """任务状态枚举 — 定义任务生命周期的所有状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """任务优先级枚举 — 对应全局优先级队列的四个级别。"""

    USER_SYNC = "user_sync"
    TASK_PRIMARY = "task_primary"
    TASK_RETRY = "task_retry"
    BATCH = "batch"


# 合法状态转换映射
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    },
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


@dataclass
class Task:
    """任务领域组件。

    Attributes:
        task_id: 任务ID。
        workflow_name: 工作流名称。
        input_data: 输入数据。
        status: 当前状态。
        priority: 优先级。
        correlation_id: 用于关联同一业务链路的关联 ID。
        result: 处理结果。
        error: 错误信息。
        created_at: 创建时间。
        started_at: 于。
        completed_at: 已完成于。
        metadata: 附加元数据。
    """

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_name: str = ""
    input_data: dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.TASK_PRIMARY
    correlation_id: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验并补全初始化后的字段。"""
        if not self.correlation_id:
            self.correlation_id = self.task_id

    @staticmethod
    def can_transition(from_status: TaskStatus, to_status: TaskStatus) -> bool:
        """检查状态转换是否合法。

        Args:
            from_status: 从状态。
            to_status: 到状态。

        Returns:
            操作是否成功。
        """
        return to_status in VALID_TRANSITIONS.get(from_status, set())

    def to_dict(self) -> dict[str, Any]:
        """处理到字典。

        Returns:
            结构化结果字典。
        """
        return {
            "task_id": self.task_id,
            "workflow_name": self.workflow_name,
            "input_data": self.input_data,
            "status": self.status.value,
            "priority": self.priority.value,
            "correlation_id": self.correlation_id,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        """从字典构造当前对象。

        Args:
            data: 待处理数据。

        Returns:
            任务结果。
        """
        return cls(
            task_id=data.get("task_id", str(uuid.uuid4())),
            workflow_name=data.get("workflow_name", ""),
            input_data=data.get("input_data", {}),
            status=TaskStatus(data.get("status", "pending")),
            priority=TaskPriority(data.get("priority", "task_primary")),
            correlation_id=data.get("correlation_id", ""),
            result=data.get("result", {}),
            error=data.get("error", ""),
            created_at=data.get("created_at", time.time()),
            started_at=data.get("started_at", 0.0),
            completed_at=data.get("completed_at", 0.0),
            metadata=data.get("metadata", {}),
        )
