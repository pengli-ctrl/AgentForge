"""超时模块。"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Coroutine

logger = logging.getLogger(__name__)


@dataclass
class TimeoutConfig:
    """超时配置模型。

    Attributes:
        llm_timeout: LLM超时。
        agent_timeout: 智能体超时。
        dag_timeout: DAG超时。
    """

    llm_timeout: float = 10.0
    agent_timeout: float = 30.0
    dag_timeout: float = 300.0

    def validate(self) -> None:
        """校验超时。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if not (self.llm_timeout < self.agent_timeout < self.dag_timeout):
            raise ValueError(
                f"Timeout hierarchy violated: llm({self.llm_timeout}) < "
                f"agent({self.agent_timeout}) < dag({self.dag_timeout}) required"
            )

    def ratios(self) -> dict[str, float]:
        """计算各层超时的时间比例。

        Returns:
            结构化结果字典。
        """
        return {
            "agent_to_llm": round(self.agent_timeout / self.llm_timeout, 1),
            "dag_to_agent": round(self.dag_timeout / self.agent_timeout, 1),
            "dag_to_llm": round(self.dag_timeout / self.llm_timeout, 1),
        }


class TimeoutManager:
    """超时领域组件。"""

    def __init__(self, config: TimeoutConfig | None = None):
        """初始化 TimeoutManager。

        Args:
            config: 组件配置。
        """
        self._config = config or TimeoutConfig()
        self._config.validate()
        self._timeout_count = {"llm": 0, "agent": 0, "dag": 0}

    async def execute_with_llm_timeout(self, coro: Coroutine) -> Any:
        """执行使用LLM超时。

        Args:
            coro: 输入参数。

        Returns:
            处理结果对象。

        Raises:
            Exception: 操作无法完成时抛出。
        """
        try:
            return await asyncio.wait_for(coro, timeout=self._config.llm_timeout)
        except asyncio.TimeoutError:
            self._timeout_count["llm"] += 1
            logger.warning("L1 LLM timeout (%.1fs) exceeded", self._config.llm_timeout)
            raise

    async def execute_with_agent_timeout(self, coro: Coroutine) -> Any:
        """执行及智能体超时。

        Args:
            coro: 输入参数。

        Returns:
            处理结果对象。

        Raises:
            Exception: 操作无法完成时抛出。
        """
        try:
            return await asyncio.wait_for(coro, timeout=self._config.agent_timeout)
        except asyncio.TimeoutError:
            self._timeout_count["agent"] += 1
            logger.warning("L2 Agent timeout (%.1fs) exceeded", self._config.agent_timeout)
            raise

    async def execute_with_dag_timeout(self, coro: Coroutine) -> Any:
        """执行使用DAG超时。

        Args:
            coro: 输入参数。

        Returns:
            处理结果对象。

        Raises:
            Exception: 操作无法完成时抛出。
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
        """执行配置。

        Returns:
            超时配置结果。
        """
        return self._config

    @property
    def timeout_stats(self) -> dict[str, int]:
        """返回超时统计。

        Returns:
            结构化结果字典。
        """
        return dict(self._timeout_count)
