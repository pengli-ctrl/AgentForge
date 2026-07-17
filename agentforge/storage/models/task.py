"""Task 数据模型 — 任务生命周期的数据结构定义。

定义了任务的状态枚举、优先级枚举和 Task dataclass。
任务状态机：PENDING → RUNNING → COMPLETED / FAILED / CANCELLED。

状态转换规则：
    PENDING → RUNNING（任务开始执行）
    RUNNING → COMPLETED（任务成功完成）
    RUNNING → FAILED（任务执行失败）
    RUNNING → CANCELLED（用户取消任务）
    PENDING → CANCELLED（任务在排队时被取消）

不允许的状态转换会被 TaskStore 拒绝。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    """任务状态枚举 — 定义任务生命周期的所有状态。

    状态流转：PENDING → RUNNING → COMPLETED / FAILED / CANCELLED
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """任务优先级枚举 — 对应全局优先级队列的四个级别。

    优先级从高到低：user_sync > task_primary > task_retry > batch。
    """

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
    """任务数据模型 — 表示一个提交到 AgentForge 的工作单元。

    每个任务包含输入数据、工作流配置、执行状态和结果。
    任务通过 correlation_id 与事件总线上流转的事件关联。

    Attributes:
        task_id: 任务唯一标识（UUID）。
        workflow_name: 工作流名称（对应 configs/workflows/ 下的 YAML）。
        input_data: 任务输入数据（代码内容、文件路径等）。
        status: 当前任务状态。
        priority: 任务优先级。
        correlation_id: 关联 ID，贯穿事件总线的所有事件。
        result: 任务执行结果（COMPLETED 状态时填充）。
        error: 任务失败原因（FAILED 状态时填充）。
        created_at: 任务创建时间戳。
        started_at: 任务开始执行时间戳。
        completed_at: 任务完成时间戳。
        metadata: 额外元数据（如提交者、PR 编号等）。
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
        """确保 correlation_id 非空。"""
        if not self.correlation_id:
            self.correlation_id = self.task_id

    @staticmethod
    def can_transition(from_status: TaskStatus, to_status: TaskStatus) -> bool:
        """检查状态转换是否合法。

        Args:
            from_status: 当前状态。
            to_status: 目标状态。

        Returns:
            是否允许从 from_status 转换到 to_status。
        """
        return to_status in VALID_TRANSITIONS.get(from_status, set())

    def to_dict(self) -> dict[str, Any]:
        """将 Task 序列化为字典。

        Returns:
            包含所有字段的字典，枚举值转为字符串。
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
        """从字典反序列化 Task。

        Args:
            data: 包含 Task 字段的字典。

        Returns:
            Task 实例。
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
