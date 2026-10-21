"""智能体模块。"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from agentforge.core.memory import MemoryConfig, MemoryManager
from agentforge.observability.tracing import Span, SpanStatus
from agentforge.orchestration.timeout import TimeoutConfig, TimeoutManager

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """智能体运行状态枚举。"""

    IDLE = "idle"  # 空闲状态。
    RUNNING = "running"
    DEGRADED = "degraded"  # 降级状态。
    FAILED = "failed"
    TIMEOUT = "timeout"  # 超时状态。


_AGENT_STATE_TRANSITIONS = {
    AgentState.IDLE: {AgentState.RUNNING},
    AgentState.RUNNING: {
        AgentState.IDLE,
        AgentState.DEGRADED,
        AgentState.FAILED,
        AgentState.TIMEOUT,
    },
    AgentState.DEGRADED: {AgentState.IDLE, AgentState.FAILED},
    AgentState.FAILED: {AgentState.IDLE},
    AgentState.TIMEOUT: {AgentState.IDLE, AgentState.RUNNING},
}


@dataclass
class Tool:
    """工具领域组件。

    Attributes:
        name: 名称。
        description: 描述信息。
        parameters: 参数。
        required: 是否必填。
    """

    name: str
    description: str
    parameters: dict = field(default_factory=dict)
    required: bool = True


@dataclass
class AgentResult:
    """智能体结果领域组件。

    Attributes:
        success: 是否成功。
        data: 数据内容。
        error: 错误信息。
        degraded: 是否降级。
        token_usage: 令牌用量。
        cost: 成本。
        latency_ms: 延迟，单位为毫秒。
        span: 链路片段。
    """

    success: bool
    data: dict = field(default_factory=dict)
    error: Optional[str] = None
    degraded: bool = False
    token_usage: dict = field(default_factory=dict)
    cost: float = 0.0
    latency_ms: float = 0.0
    span: Optional[Span] = None


class BaseAgent(ABC):
    """智能体运行时基类，负责状态、记忆、工具、链路追踪和容错。"""

    def __init__(
        self,
        name: str,
        memory_config: Optional[MemoryConfig] = None,
        timeout_config: Optional[TimeoutConfig] = None,
    ):
        """初始化 BaseAgent。

        Args:
            name: 资源或对象名称。
            memory_config: 记忆配置。
            timeout_config: 超时配置。
        """
        self._name = name
        self._state = AgentState.IDLE
        self._memory = MemoryManager(
            config=memory_config or MemoryConfig(),
            session_id=f"agent-{name}",
        )
        self._timeout_mgr = TimeoutManager(timeout_config or TimeoutConfig())
        self._execution_count = 0
        self._error_count = 0
        self._last_error: Optional[str] = None

    @abstractmethod
    async def execute(self, input_data: dict) -> dict:
        """执行智能体的具体任务实现。

        Args:
            input_data: 输入数据。

        Returns:
            结构化结果字典。
        """
        ...

    def get_tools(self) -> list[Tool]:
        """获取工具。

        Returns:
            结果列表。
        """
        return []

    def get_memory_config(self) -> MemoryConfig:
        """读取记忆配置。

        Returns:
            记忆配置结果。
        """
        return MemoryConfig()

    def validate_input(self, input_data: dict) -> bool:
        """校验输入。

        Args:
            input_data: 输入数据。

        Returns:
            操作是否成功。
        """
        if not isinstance(input_data, dict):
            return False

        return "query" in input_data

    def on_error(self, error: Exception) -> dict:
        """处理错误。

        Args:
            error: 错误。

        Returns:
            结构化结果字典。
        """
        logger.warning("Agent[%s] error: %s", self._name, str(error), exc_info=True)
        return {
            "result": None,
            "error": str(error),
            "degraded": True,
            "fallback": "default_error_response",
        }

    async def run(
        self,
        input_data: dict,
        span: Optional[Span] = None,
    ) -> AgentResult:
        """运行基础智能体。

        Args:
            input_data: 输入数据。
            span: 链路片段对象。

        Returns:
            智能体结果结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        start_time = time.monotonic()
        self._execution_count += 1

        if self._state == AgentState.RUNNING:
            return AgentResult(
                success=False,
                error=f"Agent[{self._name}] is already running",
            )
        self._transition_to(AgentState.RUNNING)

        result_data: dict = {}
        status = SpanStatus.OK

        try:
            if not self.validate_input(input_data):
                raise ValueError(f"Invalid input for Agent[{self._name}]")

            session_context = await self._memory.read("short_term", "session_context")
            if session_context:
                input_data["session_context"] = session_context

            result_data = await self._timeout_mgr.execute_with_agent_timeout(
                self.execute(input_data)
            )

            # 获取结果。
            await self._memory.write("short_term", f"last_output_{self._name}", result_data)

        except asyncio.TimeoutError:
            self._transition_to(AgentState.TIMEOUT)
            self._error_count += 1
            self._last_error = "Agent execution timed out"
            status = SpanStatus.TIMEOUT
            result_data = self.on_error(asyncio.TimeoutError("Agent timeout"))

        except Exception as e:
            self._transition_to(AgentState.FAILED)
            self._error_count += 1
            self._last_error = str(e)
            status = SpanStatus.ERROR
            result_data = self.on_error(e)

        finally:
            await self._memory.clear_working()

            if span:
                await self._end_agent_span(span, result_data, status)

        # 获取结果。
        elapsed_ms = (time.monotonic() - start_time) * 1000
        success = status == SpanStatus.OK or status == SpanStatus.DEGRADED
        degraded = result_data.get("degraded", False)

        # 就绪状态。
        # 失败状态。
        if self._state == AgentState.TIMEOUT or status == SpanStatus.TIMEOUT:
            # 超时状态。
            # 超时状态。
            pass
        elif self._state == AgentState.FAILED or status == SpanStatus.ERROR:
            pass
        elif degraded:
            status = SpanStatus.DEGRADED
            self._transition_to(AgentState.DEGRADED)
        else:
            self._transition_to(AgentState.IDLE)

        return AgentResult(
            success=success,
            data=result_data,
            error=self._last_error if not success else None,
            degraded=degraded,
            token_usage=result_data.get("tokens", {}),
            cost=result_data.get("cost", 0.0),
            latency_ms=elapsed_ms,
            span=span,
        )

    def _transition_to(self, new_state: AgentState) -> None:
        """迁移到。

        Args:
            new_state: 状态。
        """
        valid = _AGENT_STATE_TRANSITIONS.get(self._state, set())

        if new_state not in valid:
            logger.warning(
                "Agent[%s] invalid transition: %s → %s (allowed: %s)",
                self._name,
                self._state.value,
                new_state.value,
                {s.value for s in valid},
            )
            return

        self._state = new_state

    async def _end_agent_span(self, span: Span, result: dict, status: SpanStatus) -> None:
        """结束当前智能体链路片段。

        Args:
            span: 链路片段对象。
            result: 处理结果。
            status: 目标状态。
        """
        span.set_attribute("agent_name", self._name)
        span.set_attribute("execution_count", self._execution_count)
        span.set_attribute("error_count", self._error_count)
        if result.get("tokens"):
            span.set_attribute("tokens", result["tokens"])
        span.status = status

    @property
    def name(self) -> str:
        """返回对象名称。

        Returns:
            字符串结果。
        """
        return self._name

    @property
    def state(self) -> AgentState:
        """返回当前运行状态。

        Returns:
            智能体状态结果。
        """
        return self._state

    @property
    def memory(self) -> MemoryManager:
        """执行记忆。

        Returns:
            记忆管理器结果。
        """
        return self._memory

    @property
    def stats(self) -> dict:
        """获取当前统计数据。

        Returns:
            结构化结果字典。
        """
        return {
            "name": self._name,
            "state": self._state.value,
            "execution_count": self._execution_count,
            "error_count": self._error_count,
            "last_error": self._last_error,
        }

    def reset(self) -> None:
        """重置当前状态。"""
        self._state = AgentState.IDLE
        self._last_error = None


class Agent:
    """智能体抽象基类，定义统一执行协议和运行时能力。"""

    def __init__(
        self,
        llm_gateway,
        name: str,
        tool_registry=None,
        max_iterations: int = 5,
        token_budget: int = 8000,
    ) -> None:
        """初始化 Agent。

        Args:
            llm_gateway: LLM 网关实例。
            name: 资源或对象名称。
            tool_registry: 工具注册表。
            max_iterations: 最大迭代次数。
            token_budget: 令牌预算。
        """
        self._llm_gateway = llm_gateway
        self._name = name
        self._tool_registry = tool_registry
        self._max_iterations = max_iterations
        self._token_budget = token_budget
        self.prompt_template = ""

    @property
    def name(self) -> str:
        """返回对象名称。

        Returns:
            字符串结果。
        """
        return self._name

    async def execute(self, event):
        """执行核心处理逻辑并返回结果。

        Args:
            event: 待处理事件。

        Returns:
            处理结果。
        """
        from agentforge.core.event_types import AgentEvent, EventType

        try:
            relevant_context = self._extract_context(event.context_snapshot)
            task = str(event.payload.get("task") or event.payload.get("query") or "")
            messages = self._build_initial_messages(task)
            tools = self._get_tool_schemas()
            total_tokens = 0
            final_content = ""
            tool_results = []

            for _ in range(self._max_iterations):
                if total_tokens >= self._token_budget:
                    break

                response = await self._llm_gateway.chat(
                    messages,
                    tools=tools or None,
                )
                total_tokens += self._usage_tokens(response.usage)
                final_content = response.content

                if not response.tool_calls:
                    break

                messages.append({"role": "assistant", "content": response.content})
                for tool_call in response.tool_calls:
                    result = await self._execute_tool(tool_call)
                    tool_results.append(result)
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Tool observation: {result.to_json()}",
                        }
                    )

            downstream = self._build_downstream_context(
                event.context_snapshot,
                relevant_context,
                tool_results,
            )
            return AgentEvent(
                event_type=EventType.AGENT_COMPLETED,
                source_agent=self._name,
                payload={
                    "result": final_content,
                    "tokens": {"total_tokens": total_tokens},
                    "cost": 0.0,
                },
                correlation_id=event.correlation_id,
                context_snapshot=downstream,
            )
        except Exception as exc:
            logger.exception("Agent[%s] execution failed", self._name)
            return AgentEvent(
                event_type=EventType.AGENT_FAILED,
                source_agent=self._name,
                payload={"result": "", "error": str(exc)},
                correlation_id=event.correlation_id,
                context_snapshot={},
            )

    def _extract_context(self, context_snapshot: dict) -> dict:
        """提取上下文。

        Args:
            context_snapshot: 上下文快照。

        Returns:
            结构化结果字典。
        """
        return context_snapshot

    def _build_initial_messages(self, task: str) -> list[dict[str, str]]:
        """构建初始消息。

        Args:
            task: 任务对象。

        Returns:
            结果列表。
        """
        system_prompt = self.prompt_template or "You are a helpful assistant."
        try:
            system_prompt = system_prompt.format(task=task, context="{}")
        except (KeyError, ValueError):
            pass
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

    def _build_downstream_context(
        self,
        original_snapshot: dict,
        relevant_context: dict,
        tool_results: list,
    ) -> dict:
        """构建下游上下文。

        Args:
            original_snapshot: 原始上下文快照。
            relevant_context: 筛选后的相关上下文。
            tool_results: 工具执行结果列表。

        Returns:
            结构化结果字典。
        """
        return {"agent_result": {"summary": self._summarize(None, tool_results)}}

    def _summarize(self, response, tool_results: list) -> str:
        """汇总智能体。

        Args:
            response: 响应。
            tool_results: 工具执行结果列表。

        Returns:
            字符串结果。
        """
        if response is not None and bool(getattr(response, "content", None)):
            return response.content
        outputs = [result.output for result in tool_results if result.output]
        return "; ".join(outputs) if outputs else ""

    def _get_tool_schemas(self) -> list[dict]:
        """获取工具结构定义。

        Returns:
            结果列表。
        """
        if self._tool_registry is None:
            return []
        return self._tool_registry.get_schemas()

    async def _execute_tool(self, tool_call):
        """执行工具。

        Args:
            tool_call: 工具调用。

        Returns:
            处理结果。
        """
        if self._tool_registry is None:
            from agentforge.core.base_tool import ToolResult

            return ToolResult(
                success=False,
                output="",
                error=f"Tool '{tool_call.name}' is unavailable",
            )
        return await self._tool_registry.execute(tool_call.name, tool_call.arguments)

    @staticmethod
    def _usage_tokens(usage: dict) -> int:
        """统计本次执行的令牌用量。

        Args:
            usage: 用量统计数据。

        Returns:
            整数结果。
        """
        if "total_tokens" in usage:
            return int(usage.get("total_tokens", 0) or 0)
        return int(usage.get("prompt_tokens", 0) or 0) + int(usage.get("completion_tokens", 0) or 0)
