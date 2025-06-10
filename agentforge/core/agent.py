"""
Unified Agent base class — runtime layer core component.

ABC abstract base + 5 standard interfaces enabling hot-pluggable registration
of 12+ Agent types. Any concrete Agent inherits BaseAgent and implements
execute() — the DAG engine calls Agents uniformly regardless of their
internal logic.

Design rationale:
    Why a base class instead of duck typing?
    1. Type safety: DAG engine can verify Agent interfaces at registration time
    2. Cross-cutting concerns: timeout, degradation, tracing, memory — all
       Agent subclasses inherit these automatically via the template method pattern
    3. Consistent error handling: on_error() provides a uniform degradation path

    Why 5 methods instead of just execute()?
    - get_tools() lets the runtime inject appropriate tools per agent
    - get_memory_config() lets each agent declare its memory needs
    - validate_input() catches bad data early, before expensive LLM calls
    - on_error() enables graceful degradation per agent type
"""

import time
import asyncio
import logging
from enum import Enum
from abc import ABC, abstractmethod
from typing import Optional, Any
from dataclasses import dataclass, field

from agentforge.core.memory import MemoryManager, MemoryConfig
from agentforge.orchestration.timeout import TimeoutManager, TimeoutConfig
from agentforge.observability.tracing import Span, SpanType, SpanStatus

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Agent lifecycle states. State transitions are enforced."""
    IDLE = "idle"                 # Ready to accept work
    RUNNING = "running"           # Currently executing
    DEGRADED = "degraded"         # Running with degraded capabilities
    FAILED = "failed"             # Terminal failure, needs reset
    TIMEOUT = "timeout"           # Timed out, can retry

    # Valid state transitions (enforced in _transition_to)
    _TRANSITIONS = {
        IDLE: {RUNNING},
        RUNNING: {IDLE, DEGRADED, FAILED, TIMEOUT},
        DEGRADED: {IDLE, FAILED},
        FAILED: {IDLE},
        TIMEOUT: {IDLE, RUNNING},
    }


@dataclass
class Tool:
    """
    Tool descriptor for Agent tool-use.
    Agents declare which tools they need via get_tools().
    """
    name: str
    description: str
    parameters: dict = field(default_factory=dict)    # JSON Schema for params
    required: bool = True


@dataclass
class AgentResult:
    """Standardized result returned by Agent.execute()."""
    success: bool
    data: dict = field(default_factory=dict)
    error: Optional[str] = None
    degraded: bool = False                  # True if result used fallback/degraded path
    token_usage: dict = field(default_factory=dict)  # {prompt_tokens, completion_tokens, total}
    cost: float = 0.0
    latency_ms: float = 0.0
    span: Optional[Span] = None             # The AGENT span for this execution


class BaseAgent(ABC):
    """
    Abstract base class for all Agent types.

    Template method pattern: run() orchestrates the full lifecycle
    (validate → memory read → execute → memory write → trace).
    Subclasses only implement execute() and optionally override the others.

    Lifecycle per call:
        1. validate_input() — reject bad data early
        2. Memory read — populate working memory from short/long-term
        3. execute() — core Agent logic (abstract, subclass implements)
        4. Memory write — persist results to appropriate tier
        5. Error handling — on_error() if any step fails
        6. Tracing — record AgentSpan with full attributes
    """

    def __init__(
        self,
        name: str,
        memory_config: Optional[MemoryConfig] = None,
        timeout_config: Optional[TimeoutConfig] = None,
    ):
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

    # ── Core interface (subclass must implement) ────────────────────────

    @abstractmethod
    async def execute(self, input_data: dict) -> dict:
        """
        Core Agent logic. Subclasses implement their specific behavior here.

        Args:
            input_data: Validated input dict. Always contains at least:
                - "query": str — the user/system query
                - "context": dict — contextual data from upstream nodes

        Returns:
            Result dict. Must contain at least:
                - "result": Any — the primary output
                - Optionally: "tokens", "cost", "metadata"
        """
        ...

    # ── Optional overrides (default implementations provided) ───────────

    def get_tools(self) -> list[Tool]:
        """
        Return list of tools this Agent can use.
        Override to declare agent-specific tools (search, code_exec, etc.).
        Default: no tools (pure reasoning agent).
        """
        return []

    def get_memory_config(self) -> MemoryConfig:
        """
        Return this Agent's memory configuration.
        Override to customize which memory tiers are enabled.
        Default: working + short-term, no long-term.
        """
        return MemoryConfig()

    def validate_input(self, input_data: dict) -> bool:
        """
        Validate input before execution. Reject early to avoid expensive LLM calls.
        Default: check required keys exist.
        """
        if not isinstance(input_data, dict):
            return False
        # Every agent expects at least a "query" field
        return "query" in input_data

    def on_error(self, error: Exception) -> dict:
        """
        Handle execution errors. Default: return degraded result.
        Override for agent-specific error recovery.
        """
        logger.warning(
            "Agent[%s] error: %s", self._name, str(error), exc_info=True
        )
        return {
            "result": None,
            "error": str(error),
            "degraded": True,
            "fallback": "default_error_response",
        }

    # ── Template method: full execution lifecycle ───────────────────────

    async def run(
        self,
        input_data: dict,
        span: Optional[Span] = None,
    ) -> AgentResult:
        """
        Full Agent lifecycle: validate → execute → trace.

        This is what the DAG engine calls. Not meant to be overridden.
        """
        start_time = time.monotonic()
        self._execution_count += 1

        # State check
        if self._state == AgentState.RUNNING:
            return AgentResult(
                success=False,
                error=f"Agent[{self._name}] is already running",
            )
        self._transition_to(AgentState.RUNNING)

        result_data: dict = {}
        status = SpanStatus.OK

        try:
            # Step 1: Input validation
            if not self.validate_input(input_data):
                raise ValueError(f"Invalid input for Agent[{self._name}]")

            # Step 2: Read from short-term memory (if enabled)
            session_context = await self._memory.read("short_term", "session_context")
            if session_context:
                input_data["session_context"] = session_context

            # Step 3: Execute with agent-level timeout (30s default)
            result_data = await self._timeout_mgr.execute_with_agent_timeout(
                self.execute(input_data)
            )

            # Step 4: Write result to short-term memory
            await self._memory.write("short_term", f"last_output_{self._name}", result_data)

        except asyncio.TimeoutError:
            self._transition_to(AgentState.TIMEOUT)
            self._error_count += 1
            self._last_error = "Agent execution timed out"
            status = SpanStatus.TIMEOUT
            result_data = self.on_error(asyncio.TimeoutError("Agent timeout"))

        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            status = SpanStatus.ERROR
            result_data = self.on_error(e)

        finally:
            # Step 5: Clear working memory after each execution
            await self._memory.clear_working()

            # Step 6: End span if provided
            if span:
                await self._end_agent_span(span, result_data, status)

        # Compute result
        elapsed_ms = (time.monotonic() - start_time) * 1000
        success = status == SpanStatus.OK or status == SpanStatus.DEGRADED
        degraded = result_data.get("degraded", False)

        if degraded and status == SpanStatus.OK:
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

    # ── Internal helpers ────────────────────────────────────────────────

    def _transition_to(self, new_state: AgentState) -> None:
        """Enforce valid state transitions."""
        valid = AgentState._TRANSITIONS.get(self._state, set())
        if new_state not in valid:
            logger.warning(
                "Agent[%s] invalid transition: %s → %s (allowed: %s)",
                self._name, self._state.value, new_state.value,
                {s.value for s in valid},
            )
        self._state = new_state

    async def _end_agent_span(
        self, span: Span, result: dict, status: SpanStatus
    ) -> None:
        """Finalize the Agent span with execution metrics."""
        span.set_attribute("agent_name", self._name)
        span.set_attribute("execution_count", self._execution_count)
        span.set_attribute("error_count", self._error_count)
        if result.get("tokens"):
            span.set_attribute("tokens", result["tokens"])
        span.status = status

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def memory(self) -> MemoryManager:
        return self._memory

    @property
    def stats(self) -> dict:
        return {
            "name": self._name,
            "state": self._state.value,
            "execution_count": self._execution_count,
            "error_count": self._error_count,
            "last_error": self._last_error,
        }

    def reset(self) -> None:
        """Reset agent to IDLE state. Used after FAILED/TIMEOUT recovery."""
        self._state = AgentState.IDLE
        self._last_error = None
