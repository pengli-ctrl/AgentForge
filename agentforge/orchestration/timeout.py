"""AgentForge 编排执行层：timeout。

本模块负责 timeout 相关能力，是 编排执行层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：TimeoutConfig、TimeoutManager。
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Coroutine

logger = logging.getLogger(__name__)


@dataclass
class TimeoutConfig:
    """TimeoutConfig。

    TimeoutConfig 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - llm_timeout: float。
    - agent_timeout: float。
    - dag_timeout: float。
    - 方法 validate()。
    - 方法 ratios()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    llm_timeout: float = 10.0  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    agent_timeout: float = 30.0  # Agent 注册与查询。
    dag_timeout: float = 300.0  # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    def validate(self) -> None:
        """执行 validate 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if not (self.llm_timeout < self.agent_timeout < self.dag_timeout):
            raise ValueError(
                f"Timeout hierarchy violated: llm({self.llm_timeout}) < "
                f"agent({self.agent_timeout}) < dag({self.dag_timeout}) required"
            )

    def ratios(self) -> dict[str, float]:
        """执行 ratios 对应的逻辑，并返回处理结果。

        Returns:
            dict[str, float]，函数执行后的结果。
        """
        return {
            "agent_to_llm": round(self.agent_timeout / self.llm_timeout, 1),
            "dag_to_agent": round(self.dag_timeout / self.agent_timeout, 1),
            "dag_to_llm": round(self.dag_timeout / self.llm_timeout, 1),
        }


class TimeoutManager:
    """TimeoutManager。

    TimeoutManager 是核心运行时组件，负责状态管理、调度和跨模块协作。

    主要成员：
    - 方法 execute_with_llm_timeout()。
    - 方法 execute_with_agent_timeout()。
    - 方法 execute_with_dag_timeout()。
    - 方法 config()。
    - 方法 timeout_stats()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(self, config: TimeoutConfig | None = None):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            config: TimeoutConfig | None，调用方传入的 config 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._config = config or TimeoutConfig()
        self._config.validate()
        self._timeout_count = {"llm": 0, "agent": 0, "dag": 0}

    async def execute_with_llm_timeout(self, coro: Coroutine) -> Any:
        """执行 execute_with_llm_timeout 对应的逻辑，并返回处理结果。

        Args:
            coro: Coroutine，调用方传入的 coro 参数。

        Returns:
            Any，函数执行后的结果。
        """
        try:
            return await asyncio.wait_for(coro, timeout=self._config.llm_timeout)
        except asyncio.TimeoutError:
            self._timeout_count["llm"] += 1
            logger.warning("L1 LLM timeout (%.1fs) exceeded", self._config.llm_timeout)
            raise

    async def execute_with_agent_timeout(self, coro: Coroutine) -> Any:
        """执行 execute_with_agent_timeout 对应的逻辑，并返回处理结果。

        Args:
            coro: Coroutine，调用方传入的 coro 参数。

        Returns:
            Any，函数执行后的结果。
        """
        try:
            return await asyncio.wait_for(coro, timeout=self._config.agent_timeout)
        except asyncio.TimeoutError:
            self._timeout_count["agent"] += 1
            logger.warning("L2 Agent timeout (%.1fs) exceeded", self._config.agent_timeout)
            raise

    async def execute_with_dag_timeout(self, coro: Coroutine) -> Any:
        """执行 execute_with_dag_timeout 对应的逻辑，并返回处理结果。

        Args:
            coro: Coroutine，调用方传入的 coro 参数。

        Returns:
            Any，函数执行后的结果。
        """
        try:
            return await asyncio.wait_for(coro, timeout=self._config.dag_timeout)
        except asyncio.TimeoutError:
            self._timeout_count["dag"] += 1
            logger.critical(
                "L3 DAG timeout (%.1fs) — all running nodes cancelled, "
                "returning partial results",
                self._config.dag_timeout,
            )
            raise

    @property
    def config(self) -> TimeoutConfig:
        """执行 config 对应的逻辑，并返回处理结果。

        Returns:
            TimeoutConfig，函数执行后的结果。
        """
        return self._config

    @property
    def timeout_stats(self) -> dict[str, int]:
        """执行 timeout_stats 对应的逻辑，并返回处理结果。

        Returns:
            dict[str, int]，函数执行后的结果。
        """
        return dict(self._timeout_count)
