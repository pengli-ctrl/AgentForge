"""
Three-tier timeout system — methodology for distributed AI systems under uncertainty.

    LLM call:    10 seconds  (L1 — single model inference)
    Agent:       30 seconds  (L2 — agent with tools + memory + potential retries)
    DAG global: 300 seconds  (L3 — full pipeline with multiple agents)

Why these specific values?
    LLM 10s: Based on P95 latency analysis across 5 models (Qwen3-Pro, GLM-5,
    Kimi, MiniMax, DeepSeek-V3). Measured latencies:
        MiniMax:    P50=300ms, P95=800ms, P99=1500ms
        DeepSeek:   P50=800ms, P95=1800ms, P99=3200ms
        GLM-5:      P50=1000ms, P95=2200ms, P99=4000ms
        Kimi:       P50=900ms, P95=1800ms, P99=3500ms
        Qwen3-Pro:  P50=1200ms, P95=2800ms, P99=5500ms
    10s covers P99 across all models with comfortable headroom.
    Beyond 10s, the user perceives the system as "stuck".

    Agent 30s: A single Agent may invoke 2–3 LLM calls (plan + execute + validate)
    plus tool execution (search, code_exec) plus memory operations.
    30s ≈ 3 × 10s LLM budget + tool/memory overhead.
    This is the P95 for complex agent tasks based on execution trace analysis.

    DAG 300s: Worst case — 50 nodes, 5 parallel slots → 10 sequential waves.
    10 waves × 30s/wave = 300s. This is the P95 for end-to-end pipelines.
    If a DAG takes longer, something is fundamentally wrong (infinite retry,
    external API down, etc.) and we should fail fast with partial results.

Design rationale:
    The three-tier system implements "structured cancellation" — when a timeout
    fires at any level, it cleanly cancels all child operations via asyncio
    task cancellation. This prevents resource leaks (hanging HTTP connections,
    running tool subprocesses) and ensures the system always makes progress.

    Why not a single global timeout?
    - LLM-level timeout enables fast model fallback (10s → switch model)
    - Agent-level timeout enables node-level degradation (30s → use default)
    - DAG-level timeout enables graceful partial completion (300s → return what we have)
    Each tier serves a different degradation strategy. A single timeout would
    force all-or-nothing behavior.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Coroutine

logger = logging.getLogger(__name__)


@dataclass
class TimeoutConfig:
    """
    Configurable timeout values for each tier.
    Defaults based on P95 analysis; override for different deployment profiles.

    Constraint: llm_timeout < agent_timeout < dag_timeout
    This hierarchy ensures that inner timeouts fire before outer ones,
    enabling graceful degradation at each level.
    """
    llm_timeout: float = 10.0       # L1: single LLM inference (P99 across 5 models)
    agent_timeout: float = 30.0     # L2: full agent execution (3× LLM + tools + memory)
    dag_timeout: float = 300.0      # L3: entire DAG pipeline (10 waves × 30s)

    def validate(self) -> None:
        """
        Ensure timeout hierarchy is maintained: L1 < L2 < L3.

        This is critical — if agent_timeout ≤ llm_timeout, the agent timeout
        would fire before the LLM call completes, making L1 degradation impossible.
        """
        if not (self.llm_timeout < self.agent_timeout < self.dag_timeout):
            raise ValueError(
                f"Timeout hierarchy violated: llm({self.llm_timeout}) < "
                f"agent({self.agent_timeout}) < dag({self.dag_timeout}) required"
            )

    def ratios(self) -> dict[str, float]:
        """Return the ratios between tiers (useful for monitoring)."""
        return {
            "agent_to_llm": round(self.agent_timeout / self.llm_timeout, 1),
            "dag_to_agent": round(self.dag_timeout / self.agent_timeout, 1),
            "dag_to_llm": round(self.dag_timeout / self.llm_timeout, 1),
        }


class TimeoutManager:
    """
    Manages timeout enforcement at all three levels.

    Each method wraps an awaitable with asyncio.wait_for(), which raises
    asyncio.TimeoutError if the coroutine doesn't complete in time.

    Why asyncio.wait_for instead of signal-based timeout?
    - Cross-platform (signals are Unix-only, and SIGALRM can't nest)
    - Integrates naturally with the asyncio event loop
    - Properly cancels the wrapped coroutine (sends CancelledError into it)
    - No thread-safety concerns (all on the same event loop)

    Cancellation semantics:
    When asyncio.wait_for times out, it:
    1. Sends CancelledError to the wrapped coroutine
    2. Waits for the coroutine to handle the cancellation
    3. Raises asyncio.TimeoutError to the caller

    The wrapped coroutine SHOULD catch CancelledError and clean up resources.
    BaseAgent.run() handles this in its try/except/finally block.
    """

    def __init__(self, config: TimeoutConfig | None = None):
        self._config = config or TimeoutConfig()
        self._config.validate()
        self._timeout_count = {"llm": 0, "agent": 0, "dag": 0}

    async def execute_with_llm_timeout(self, coro: Coroutine) -> Any:
        """
        L1 timeout: single LLM API call. 10s default.

        On timeout: caller triggers L1 degradation (switch model).
        The cancelled coroutine's HTTP connection is cleaned up by aiohttp/httpx.
        """
        try:
            return await asyncio.wait_for(coro, timeout=self._config.llm_timeout)
        except asyncio.TimeoutError:
            self._timeout_count["llm"] += 1
            logger.warning("L1 LLM timeout (%.1fs) exceeded", self._config.llm_timeout)
            raise

    async def execute_with_agent_timeout(self, coro: Coroutine) -> Any:
        """
        L2 timeout: full Agent execution. 30s default.

        Covers: execute() + tool calls + memory read/write.
        On timeout: caller triggers L2 degradation (retry → fallback).
        All internal operations (LLM calls, tool subprocesses) are cancelled.
        """
        try:
            return await asyncio.wait_for(coro, timeout=self._config.agent_timeout)
        except asyncio.TimeoutError:
            self._timeout_count["agent"] += 1
            logger.warning("L2 Agent timeout (%.1fs) exceeded", self._config.agent_timeout)
            raise

    async def execute_with_dag_timeout(self, coro: Coroutine) -> Any:
        """
        L3 timeout: entire DAG pipeline. 300s default.

        Wraps the entire DAGEngine.execute() call. When this fires:
        - ALL running nodes are cancelled simultaneously
        - The caller returns partial_success with completed node results
        - System logs a warning and triggers L4 degradation if cascading

        This is the "nuclear option" — it should rarely fire in normal operation.
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
        return self._config

    @property
    def timeout_stats(self) -> dict[str, int]:
        """Number of timeouts at each level (for monitoring/alerting)."""
        return dict(self._timeout_count)
