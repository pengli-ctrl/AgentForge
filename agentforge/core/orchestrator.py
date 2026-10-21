"""编排器模块。"""

from __future__ import annotations

import logging
import warnings
from typing import Any

logger = logging.getLogger(__name__)


class Orchestrator:
    """编排器相关组件。"""

    def __init__(self, state_store: Any = None) -> None:
        """初始化 Orchestrator。

        Args:
            state_store: 状态存储。
        """
        warnings.warn(
            "Orchestrator (V2) is deprecated. Use EventBus + dynamic routing instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.agents: dict[str, Any] = {}
        self.pipeline: list[str] = []  # 写死的执行顺序
        self.state_store = state_store

    def register_agent(self, name: str, agent: Any) -> None:
        """注册智能体。

        Args:
            name: 资源或对象名称。
            agent: 智能体。
        """
        self.agents[name] = agent

    def set_pipeline(self, steps: list[str]) -> None:
        """设置执行管道顺序。

        Args:
            steps: 输入参数。
        """
        self.pipeline = steps

    async def execute(self, task: str) -> dict[str, Any]:
        """执行核心处理逻辑并返回结果。

        Args:
            task: 任务对象。

        Returns:
            结构化结果字典。
        """
        results: dict[str, Any] = {}
        context: dict[str, Any] = await self._load_or_create(task)

        for step_name in self.pipeline:
            agent = self.agents[step_name]
            # 把完整的 context 传给 Agent（问题根源：context 会无限膨胀）
            result = await agent.execute(context)
            results[step_name] = result
            context[f"{step_name}_result"] = result  # 每步追加，到第4步已经炸了
            await self._save(task, context)

        return results

    async def _load_or_create(self, task_id: str) -> dict[str, Any]:
        """加载或创建任务状态。

        Args:
            task_id: 任务 ID。

        Returns:
            结构化结果字典。
        """
        if self.state_store:
            return await self.state_store.load_or_create(task_id=task_id)
        return {}

    async def _save(self, task_id: str, context: dict[str, Any]) -> None:
        """保存任务状态。

        Args:
            task_id: 任务 ID。
            context: 执行上下文。
        """
        if self.state_store:
            await self.state_store.save(task_id=task_id, context=context)
