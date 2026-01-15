"""
V2 串行编排器 — 已废弃，保留用于参考和迁移。

.. deprecated::
    此模块为 V2 架构的串行编排器，存在三个根本性问题：
    1. Orchestrator 变成上帝对象（2000+ 行代码）
    2. 共享状态 context 字典无限膨胀
    3. 静态 pipeline 无法应对真实场景的分支逻辑

    V3 使用事件总线 + 动态路由替代此编排器。
    详见 agentforge.core.event_bus 和 configs/workflows/ 下的 YAML 配置。

V2 → V3 的迁移采用灰度切换，不是大爆炸：
1. 先建事件总线基础设施（2 周）
2. 逐个 Agent 迁移（4 周），从最独立的 DocGenerator 开始
3. 并行跑 2 周，V2 保留为 fallback
4. 数据迁移：V2 的 Redis 共享状态不迁移，V3 用 Context Snapshot 替代
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

logger = logging.getLogger(__name__)


class Orchestrator:
    """V2 串行编排器 — 管理多 Agent 的执行顺序和数据传递。

    .. deprecated:: 3.0.0
        使用 EventBus + 动态路由 YAML 配置替代。

    V2 的核心问题：
    - context[f"{step_name}_result"] = result 让 context 字典无限膨胀
    - 到第 4 步时，DocAgent 收到的 context 包含了所有前序步骤的原始数据
    - Prompt 又炸了，只是换了个地方炸

    Args:
        state_store: 状态存储后端（RedisStateStore 等）。
    """

    def __init__(self, state_store: Any = None) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            state_store: Any，调用方传入的 state_store 参数。

        Returns:
            None，函数执行后的结果。
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
        """注册 Agent 到编排器。

        Args:
            name: Agent 名称。
            agent: Agent 实例。
        """
        self.agents[name] = agent

    def set_pipeline(self, steps: list[str]) -> None:
        """设置执行管道顺序。

        Args:
            steps: Agent 名称列表，按执行顺序排列。
        """
        self.pipeline = steps

    async def execute(self, task: str) -> dict[str, Any]:
        """串行执行管道中的所有 Agent。

        .. warning::
            此方法存在 context 无限膨胀问题：
            每步追加结果到 context，到第 4 步时 context 已包含所有前序数据。

        Args:
            task: 任务描述。

        Returns:
            包含所有步骤结果的字典。
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
            任务上下文字典。
        """
        if self.state_store:
            return await self.state_store.load_or_create(task_id=task_id)
        return {}

    async def _save(self, task_id: str, context: dict[str, Any]) -> None:
        """保存任务状态。

        Args:
            task_id: 任务 ID。
            context: 任务上下文。
        """
        if self.state_store:
            await self.state_store.save(task_id=task_id, context=context)
