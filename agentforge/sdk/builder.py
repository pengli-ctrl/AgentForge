"""Agent 构建器 — 流式 API 构建 Agent。

提供链式调用 API 来构建 Agent 实例，
使 Agent 的创建更加直观和可读。

使用方式：
    agent = (
        AgentBuilder()
        .with_llm(llm_gateway)
        .with_tool(CodeReviewTool())
        .with_tool(SecurityScanTool())
        .with_prompt("code_review")
        .with_name("my-code-reviewer")
        .with_max_iterations(10)
        .build()
    )
"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.core.agent import Agent
from agentforge.core.base_tool import BaseTool, ToolRegistry
from agentforge.prompts.manager import PromptManager

logger = logging.getLogger(__name__)


class AgentBuilder:
    """Agent 构建器 — 流式 API 构建 Agent 实例。

    通过链式调用配置 Agent 的各个组件：
    - LLM 网关
    - 工具集
    - Prompt 模板
    - Agent 名称
    - 最大迭代次数
    - Token 预算

    Example:
        >>> agent = (
        ...     AgentBuilder()
        ...     .with_llm(llm_gateway)
        ...     .with_tool(CodeReviewTool())
        ...     .with_prompt("code_review")
        ...     .with_name("my-reviewer")
        ...     .build()
        ... )
    """

    def __init__(self) -> None:
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
            self（用于链式调用）。
        """
        self._llm_gateway = llm_gateway
        return self

    def with_tool(self, tool: BaseTool) -> AgentBuilder:
        """添加工具。

        可以多次调用以添加多个工具。

        Args:
            tool: 工具实例。

        Returns:
            self（用于链式调用）。
        """
        self._tools.append(tool)
        return self

    def with_tools(self, tools: list[BaseTool]) -> AgentBuilder:
        """批量添加工具。

        Args:
            tools: 工具实例列表。

        Returns:
            self（用于链式调用）。
        """
        self._tools.extend(tools)
        return self

    def with_prompt(self, prompt_name: str) -> AgentBuilder:
        """设置 Prompt 模板名称。

        模板从 PromptManager 加载。

        Args:
            prompt_name: Prompt 模板名称。

        Returns:
            self（用于链式调用）。
        """
        self._prompt_name = prompt_name
        return self

    def with_name(self, name: str) -> AgentBuilder:
        """设置 Agent 名称。

        Args:
            name: Agent 名称。

        Returns:
            self（用于链式调用）。
        """
        self._name = name
        return self

    def with_max_iterations(self, max_iterations: int) -> AgentBuilder:
        """设置最大迭代次数。

        Args:
            max_iterations: ReAct 循环最大迭代次数。

        Returns:
            self（用于链式调用）。
        """
        self._max_iterations = max_iterations
        return self

    def with_token_budget(self, token_budget: int) -> AgentBuilder:
        """设置 Token 预算。

        Args:
            token_budget: Prompt token 预算。

        Returns:
            self（用于链式调用）。
        """
        self._token_budget = token_budget
        return self

    def with_prompt_manager(self, manager: PromptManager) -> AgentBuilder:
        """设置 Prompt 管理器。

        Args:
            manager: PromptManager 实例。

        Returns:
            self（用于链式调用）。
        """
        self._prompt_manager = manager
        return self

    def build(self) -> Agent:
        """构建 Agent 实例。

        Returns:
            配置好的 Agent 实例。

        Raises:
            ValueError: LLM 网关未设置时抛出。
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
    """通过 AgentBuilder 构建的 Agent 实例。

    继承 Agent 基类，_build_initial_messages 使用默认实现。
    """

    def _build_initial_messages(self, task: str) -> list[dict[str, str]]:
        """构造初始消息列表。

        Args:
            task: 任务描述。

        Returns:
            消息列表。
        """
        return [
            {"role": "system", "content": self.prompt_template or "You are a helpful assistant."},
            {"role": "user", "content": task},
        ]
