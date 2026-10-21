"""构建器模块。"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.core.agent import Agent
from agentforge.core.base_tool import BaseTool, ToolRegistry
from agentforge.prompts.manager import PromptManager

logger = logging.getLogger(__name__)


class AgentBuilder:
    """智能体相关组件。"""

    def __init__(self) -> None:
        """初始化 AgentBuilder。"""
        self._llm_gateway: Any = None
        self._tools: list[BaseTool] = []
        self._prompt_name: str = ""
        self._name: str = "custom-agent"
        self._max_iterations: int = 5
        self._token_budget: int = 8000
        self._prompt_manager: PromptManager | None = None

    def with_llm(self, llm_gateway: Any) -> AgentBuilder:
        """设置 LLM 网关。

        Args:
            llm_gateway: LLM 网关实例。

        Returns:
            智能体结果。
        """
        self._llm_gateway = llm_gateway
        return self

    def with_tool(self, tool: BaseTool) -> AgentBuilder:
        """添加工具。

        Args:
            tool: 工具。

        Returns:
            智能体结果。
        """
        self._tools.append(tool)
        return self

    def with_tools(self, tools: list[BaseTool]) -> AgentBuilder:
        """批量添加工具。

        Args:
            tools: 可供模型调用的工具定义。

        Returns:
            智能体结果。
        """
        self._tools.extend(tools)
        return self

    def with_prompt(self, prompt_name: str) -> AgentBuilder:
        """处理使用提示词。

        Args:
            prompt_name: 提示词名称。

        Returns:
            智能体结果。
        """
        self._prompt_name = prompt_name
        return self

    def with_name(self, name: str) -> AgentBuilder:
        """处理使用名称。

        Args:
            name: 资源或对象名称。

        Returns:
            智能体结果。
        """
        self._name = name
        return self

    def with_max_iterations(self, max_iterations: int) -> AgentBuilder:
        """设置最大迭代次数。

        Args:
            max_iterations: 最大迭代次数。

        Returns:
            智能体结果。
        """
        self._max_iterations = max_iterations
        return self

    def with_token_budget(self, token_budget: int) -> AgentBuilder:
        """处理使用令牌预算。

        Args:
            token_budget: 令牌预算。

        Returns:
            智能体结果。
        """
        self._token_budget = token_budget
        return self

    def with_prompt_manager(self, manager: PromptManager) -> AgentBuilder:
        """处理使用提示词管理器。

        Args:
            manager: 管理器。

        Returns:
            智能体结果。
        """
        self._prompt_manager = manager
        return self

    def build(self) -> Agent:
        """构建智能体。

        Returns:
            智能体结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if self._llm_gateway is None:
            raise ValueError("LLM gateway is required. Use .with_llm() to set it.")

        # 构建工具注册表
        registry = ToolRegistry()
        for tool in self._tools:
            registry.register(tool)

        # 加载 Prompt 模板
        prompt_template = ""
        if self._prompt_name:
            manager = self._prompt_manager or PromptManager()
            try:
                prompt_template = manager.load(self._prompt_name)
            except FileNotFoundError:
                logger.warning(
                    "Prompt template not found (name=%s), using empty template",
                    self._prompt_name,
                )

        # 创建 Agent 实例
        agent = _BuiltAgent(
            llm_gateway=self._llm_gateway,
            name=self._name,
            tool_registry=registry,
            max_iterations=self._max_iterations,
            token_budget=self._token_budget,
        )
        agent.prompt_template = prompt_template

        logger.info(
            "Agent built (name=%s, tools=%d, prompt=%s, max_iter=%d)",
            self._name,
            len(self._tools),
            self._prompt_name or "none",
            self._max_iterations,
        )

        return agent


class _BuiltAgent(Agent):
    """智能体相关组件。"""

    def _build_initial_messages(self, task: str) -> list[dict[str, str]]:
        """构造初始消息列表。

        Args:
            task: 任务对象。

        Returns:
            结果列表。
        """
        return [
            {"role": "system", "content": self.prompt_template or "You are a helpful assistant."},
            {"role": "user", "content": task},
        ]
