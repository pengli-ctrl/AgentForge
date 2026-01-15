"""AgentForge 核心运行时层：agent。

本模块负责 agent 相关能力，是 核心运行时层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：AgentState、Tool、AgentResult、BaseAgent、Agent。
"""

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
    """AgentState。

    AgentState 是状态或类型枚举，用于约束系统内部取值，避免散落的字符串常量。

    主要成员：
    - IDLE: 'idle'。
    - RUNNING: 'running'。
    - DEGRADED: 'degraded'。
    - FAILED: 'failed'。
    - TIMEOUT: 'timeout'。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    IDLE = "idle"  # 就绪状态。
    RUNNING = "running"  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    DEGRADED = "degraded"  # 执行中状态。
    FAILED = "failed"  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    TIMEOUT = "timeout"  # 失败重试。


# 说明：该步骤用于实现上述逻辑并保证行为稳定。
# 说明：该步骤用于实现上述逻辑并保证行为稳定。
# 说明：该步骤用于实现上述逻辑并保证行为稳定。
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
    """Tool。

    Tool 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - name: str。
    - description: str。
    - parameters: dict。
    - required: bool。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    name: str
    description: str
    parameters: dict = field(default_factory=dict)  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    required: bool = True


@dataclass
class AgentResult:
    """AgentResult。

    AgentResult 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - success: bool。
    - data: dict。
    - error: Optional[str]。
    - degraded: bool。
    - token_usage: dict。
    - cost: float。
    - latency_ms: float。
    - span: Optional[Span]。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    success: bool
    data: dict = field(default_factory=dict)
    error: Optional[str] = None
    degraded: bool = False  # 获取结果。
    token_usage: dict = field(default_factory=dict)  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    cost: float = 0.0
    latency_ms: float = 0.0
    span: Optional[Span] = None  # Agent 注册与查询。


class BaseAgent(ABC):
    """BaseAgent。

    BaseAgent 是核心运行时组件，负责状态管理、调度和跨模块协作。

    主要成员：
    - 方法 execute()。
    - 方法 get_tools()。
    - 方法 get_memory_config()。
    - 方法 validate_input()。
    - 方法 on_error()。
    - 方法 run()。
    - 方法 name()。
    - 方法 state()。
    - 方法 memory()。
    - 方法 stats()。
    - 方法 reset()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(
        self,
        name: str,
        memory_config: Optional[MemoryConfig] = None,
        timeout_config: Optional[TimeoutConfig] = None,
    ):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            name: str，调用方传入的 name 参数。
            memory_config: Optional[MemoryConfig]，调用方传入的 memory_config 参数。
            timeout_config: Optional[TimeoutConfig]，调用方传入的 timeout_config 参数。

        Returns:
            None，函数执行后的结果。
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

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    @abstractmethod
    async def execute(self, input_data: dict) -> dict:
        """执行 execute 对应的逻辑，并返回处理结果。

        Args:
            input_data: dict，调用方传入的 input_data 参数。

        Returns:
            dict，函数执行后的结果。
        """
        ...

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    def get_tools(self) -> list[Tool]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            list[Tool]，函数执行后的结果。
        """
        return []

    def get_memory_config(self) -> MemoryConfig:
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            MemoryConfig，函数执行后的结果。
        """
        return MemoryConfig()

    def validate_input(self, input_data: dict) -> bool:
        """校验输入或状态，并返回调用方需要的结果。

        Args:
            input_data: dict，调用方传入的 input_data 参数。

        Returns:
            bool，函数执行后的结果。
        """
        if not isinstance(input_data, dict):
            return False
        # Agent 注册与查询。
        return "query" in input_data

    def on_error(self, error: Exception) -> dict:
        """执行 on_error 对应的逻辑，并返回处理结果。

        Args:
            error: Exception，调用方传入的 error 参数。

        Returns:
            dict，函数执行后的结果。
        """
        logger.warning("Agent[%s] error: %s", self._name, str(error), exc_info=True)
        return {
            "result": None,
            "error": str(error),
            "degraded": True,
            "fallback": "default_error_response",
        }

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    async def run(
        self,
        input_data: dict,
        span: Optional[Span] = None,
    ) -> AgentResult:
        """执行 run 对应的逻辑，并返回处理结果。

        Args:
            input_data: dict，调用方传入的 input_data 参数。
            span: Optional[Span]，调用方传入的 span 参数。

        Returns:
            AgentResult，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        start_time = time.monotonic()
        self._execution_count += 1

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        if self._state == AgentState.RUNNING:
            return AgentResult(
                success=False,
                error=f"Agent[{self._name}] is already running",
            )
        self._transition_to(AgentState.RUNNING)

        result_data: dict = {}
        status = SpanStatus.OK

        try:
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            if not self.validate_input(input_data):
                raise ValueError(f"Invalid input for Agent[{self._name}]")

            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            session_context = await self._memory.read("short_term", "session_context")
            if session_context:
                input_data["session_context"] = session_context

            # Agent 注册与查询。
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
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            await self._memory.clear_working()

            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            if span:
                await self._end_agent_span(span, result_data, status)

        # 获取结果。
        elapsed_ms = (time.monotonic() - start_time) * 1000
        success = status == SpanStatus.OK or status == SpanStatus.DEGRADED
        degraded = result_data.get("degraded", False)

        # 就绪状态。
        # 失败状态。
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        if self._state == AgentState.TIMEOUT or status == SpanStatus.TIMEOUT:
            # 超时状态。
            # 超时状态。
            pass
        elif self._state == AgentState.FAILED or status == SpanStatus.ERROR:
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
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

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    def _transition_to(self, new_state: AgentState) -> None:
        """执行 _transition_to 对应的逻辑，并返回处理结果。

        Args:
            new_state: AgentState，调用方传入的 new_state 参数。

        Returns:
            None，函数执行后的结果。
        """
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        valid = _AGENT_STATE_TRANSITIONS.get(self._state, set())

        if new_state not in valid:
            logger.warning(
                "Agent[%s] invalid transition: %s → %s (allowed: %s)",
                self._name,
                self._state.value,
                new_state.value,
                {s.value for s in valid},
            )
            return  # 说明：该步骤用于实现上述逻辑并保证行为稳定。

        self._state = new_state

    async def _end_agent_span(self, span: Span, result: dict, status: SpanStatus) -> None:
        """执行 _end_agent_span 对应的逻辑，并返回处理结果。

        Args:
            span: Span，调用方传入的 span 参数。
            result: dict，调用方传入的 result 参数。
            status: SpanStatus，调用方传入的 status 参数。

        Returns:
            None，函数执行后的结果。
        """
        span.set_attribute("agent_name", self._name)
        span.set_attribute("execution_count", self._execution_count)
        span.set_attribute("error_count", self._error_count)
        if result.get("tokens"):
            span.set_attribute("tokens", result["tokens"])
        span.status = status

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    @property
    def name(self) -> str:
        """执行 name 对应的逻辑，并返回处理结果。

        Returns:
            str，函数执行后的结果。
        """
        return self._name

    @property
    def state(self) -> AgentState:
        """执行 state 对应的逻辑，并返回处理结果。

        Returns:
            AgentState，函数执行后的结果。
        """
        return self._state

    @property
    def memory(self) -> MemoryManager:
        """执行 memory 对应的逻辑，并返回处理结果。

        Returns:
            MemoryManager，函数执行后的结果。
        """
        return self._memory

    @property
    def stats(self) -> dict:
        """执行 stats 对应的逻辑，并返回处理结果。

        Returns:
            dict，函数执行后的结果。
        """
        return {
            "name": self._name,
            "state": self._state.value,
            "execution_count": self._execution_count,
            "error_count": self._error_count,
            "last_error": self._last_error,
        }

    def reset(self) -> None:
        """执行 reset 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
        self._state = AgentState.IDLE
        self._last_error = None


class Agent:
    """Agent。

    Agent 是核心运行时组件，负责状态管理、调度和跨模块协作。

    主要成员：
    - 方法 name()。
    - 方法 execute()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(
        self,
        llm_gateway,
        name: str,
        tool_registry=None,
        max_iterations: int = 5,
        token_budget: int = 8000,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            llm_gateway: Any，调用方传入的 llm_gateway 参数。
            name: str，调用方传入的 name 参数。
            tool_registry: Any，调用方传入的 tool_registry 参数。
            max_iterations: int，调用方传入的 max_iterations 参数。
            token_budget: int，调用方传入的 token_budget 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._llm_gateway = llm_gateway
        self._name = name
        self._tool_registry = tool_registry
        self._max_iterations = max_iterations
        self._token_budget = token_budget
        self.prompt_template = ""

    @property
    def name(self) -> str:
        """执行 name 对应的逻辑，并返回处理结果。

        Returns:
            str，函数执行后的结果。
        """
        return self._name

    async def execute(self, event):
        """执行 execute 对应的逻辑，并返回处理结果。

        Args:
            event: Any，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
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
        """执行 _extract_context 对应的逻辑，并返回处理结果。

        Args:
            context_snapshot: dict，调用方传入的 context_snapshot 参数。

        Returns:
            dict，函数执行后的结果。
        """
        return context_snapshot

    def _build_initial_messages(self, task: str) -> list[dict[str, str]]:
        """执行 _build_initial_messages 对应的逻辑，并返回处理结果。

        Args:
            task: str，调用方传入的 task 参数。

        Returns:
            list[dict[str, str]]，函数执行后的结果。
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
        """执行 _build_downstream_context 对应的逻辑，并返回处理结果。

        Args:
            original_snapshot: dict，调用方传入的 original_snapshot 参数。
            relevant_context: dict，调用方传入的 relevant_context 参数。
            tool_results: list，调用方传入的 tool_results 参数。

        Returns:
            dict，函数执行后的结果。
        """
        return {"agent_result": {"summary": self._summarize(None, tool_results)}}

    def _summarize(self, response, tool_results: list) -> str:
        """执行 _summarize 对应的逻辑，并返回处理结果。

        Args:
            response: Any，调用方传入的 response 参数。
            tool_results: list，调用方传入的 tool_results 参数。

        Returns:
            str，函数执行后的结果。
        """
        if response is not None and bool(getattr(response, "content", None)):
            return response.content
        outputs = [result.output for result in tool_results if result.output]
        return "; ".join(outputs) if outputs else ""

    def _get_tool_schemas(self) -> list[dict]:
        """执行 _get_tool_schemas 对应的逻辑，并返回处理结果。

        Returns:
            list[dict]，函数执行后的结果。
        """
        if self._tool_registry is None:
            return []
        return self._tool_registry.get_schemas()

    async def _execute_tool(self, tool_call):
        """执行 _execute_tool 对应的逻辑，并返回处理结果。

        Args:
            tool_call: Any，调用方传入的 tool_call 参数。

        Returns:
            None，函数执行后的结果。
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
        """执行 _usage_tokens 对应的逻辑，并返回处理结果。

        Args:
            usage: dict，调用方传入的 usage 参数。

        Returns:
            int，函数执行后的结果。
        """
        if "total_tokens" in usage:
            return int(usage.get("total_tokens", 0) or 0)
        return int(usage.get("prompt_tokens", 0) or 0) + int(usage.get("completion_tokens", 0) or 0)
