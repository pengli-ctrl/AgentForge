"""
Request amplification control — three-dimensional limits preventing multi-Agent
cascade calls from overwhelming external APIs.

    Dimension 1 — DAG size:       ≤ 50 nodes per DAG
    Dimension 2 — LLM call count: ≤ 100 calls per single request
    Dimension 3 — Concurrency:    ≤ 10 active DAGs × 5 parallel nodes = 50 max concurrent slots

Why these limits?
    DAG ≤ 50: Beyond 50 nodes, the orchestration overhead (context passing,
    dependency resolution, span tracking) becomes comparable to actual
    agent execution time. Also, 50 nodes × 2 LLM calls/node = 100 LLM calls,
    hitting the per-request API budget.

    LLM calls ≤ 100: Each LLM call costs money and time. 100 calls × avg $0.01
    = $1 per request maximum. Beyond this, a single user request can bankrupt
    the service. Also prevents runaway loops.

    Concurrency ≤ 10 DAGs × 5 parallel: 10 concurrent DAGs prevent a single
    user from monopolizing the system. 5 parallel nodes per DAG prevent
    burst API calls. Combined: max 50 concurrent LLM calls system-wide.

Design rationale:
    Uses semaphore pattern (acquire/release) for concurrency control.
    Size and count checks are stateless (just compare against thresholds).
    All three checks run before DAG execution starts — fail-fast prevents
    partial execution and wasted resources.
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RequestGuard:
    """
    Three-dimensional request guard preventing API overload.

    Lifecycle:
        1. Pre-flight checks: check_dag_size, check_llm_call_count, check_concurrency
        2. acquire() — reserve a concurrency slot before DAG execution
        3. release() — free the slot after DAG completion (in finally block)

    The guard uses asyncio.Semaphore for the concurrency dimension, which
    naturally handles the wait-when-full behavior. Size and count checks
    are simple boolean guards that reject immediately.
    """

    # Hard limits — these are architectural constraints, not tunable parameters
    MAX_DAG_NODES = 50  # Max nodes in a single DAG
    MAX_LLM_CALLS_PER_REQUEST = 100  # Max LLM API calls per request
    MAX_ACTIVE_DAGS = 10  # Max concurrent DAG executions
    MAX_PARALLEL_NODES = 5  # Max parallel nodes within a single DAG

    def __init__(
        self,
        max_active_dags: Optional[int] = None,
        max_parallel_nodes: Optional[int] = None,
    ):
        """
        Args:
            max_active_dags: Override max concurrent DAGs (default: 10).
            max_parallel_nodes: Override max parallel nodes per DAG (default: 5).
        """
        self._max_active = max_active_dags or self.MAX_ACTIVE_DAGS
        self._max_parallel = max_parallel_nodes or self.MAX_PARALLEL_NODES
        # Semaphore limits total concurrent DAG-node slots to max_active × max_parallel
        self._semaphore = asyncio.Semaphore(self._max_active * self._max_parallel)
        # Track active DAG count separately (for monitoring)
        self._active_dag_count = 0
        self._dag_count_lock = asyncio.Lock()
        # Track LLM call count per request (caller provides this)
        self._llm_call_counts: dict[str, int] = {}  # correlation_id → count

    # ── Pre-flight checks (stateless, instant) ─────────────────────────

    def check_dag_size(self, node_count: int) -> bool:
        """
        Check if DAG size is within limits.

        Dimension 1: DAG ≤ 50 nodes.
        Rationale: beyond 50, orchestration overhead dominates and the
        DAG becomes too complex to debug. Suggest splitting into sub-DAGs.

        Returns:
            True if within limits, False if rejected.
        """
        if node_count > self.MAX_DAG_NODES:
            logger.warning(
                "DAG size check FAILED: %d nodes > %d max. " "Consider splitting into sub-DAGs.",
                node_count,
                self.MAX_DAG_NODES,
            )
            return False
        return True

    def check_llm_call_count(self, current_count: int) -> bool:
        """
        Check if LLM call count for this request is within budget.

        Dimension 2: ≤ 100 LLM calls per request.
        Rationale: cost control ($1/request max) and loop prevention.
        Called by DAGEngine before each LLM invocation.

        Returns:
            True if within budget, False if rejected.
        """
        if current_count > self.MAX_LLM_CALLS_PER_REQUEST:
            logger.warning(
                "LLM call count check FAILED: %d calls > %d max. " "Request budget exhausted.",
                current_count,
                self.MAX_LLM_CALLS_PER_REQUEST,
            )
            return False
        return True

    def check_concurrency(self, active_dags: int, parallel_nodes: int) -> bool:
        """
        Check if system concurrency limits are respected.

        Dimension 3: ≤ 10 active DAGs, ≤ 5 parallel nodes per DAG.
        Combined max: 10 × 5 = 50 concurrent LLM calls system-wide.
        Rationale: prevents single-user monopolization and API rate limit hits.

        Returns:
            True if within limits, False if rejected.
        """
        if active_dags > self._max_active:
            logger.warning(
                "Concurrency check FAILED: %d active DAGs > %d max",
                active_dags,
                self._max_active,
            )
            return False

        if parallel_nodes > self._max_parallel:
            logger.warning(
                "Concurrency check FAILED: %d parallel nodes > %d max",
                parallel_nodes,
                self._max_parallel,
            )
            return False

        return True

    # ── Semaphore-based concurrency control ─────────────────────────────

    async def acquire(self) -> bool:
        """
        Acquire a concurrency slot before starting a DAG.

        Returns True if acquired, False if system is at capacity.
        Does NOT block — returns immediately. Use try_acquire() for
        non-blocking behavior.
        """
        acquired = self._semaphore._value > 0  # peek without blocking
        if acquired:
            await self._semaphore.acquire()
            async with self._dag_count_lock:
                self._active_dag_count += 1
            return True
        else:
            logger.warning(
                "RequestGuard: no slots available (%d/%d DAGs active)",
                self._active_dag_count,
                self._max_active,
            )
            return False

    async def release(self) -> None:
        """Release a concurrency slot after DAG completion. Always call in finally."""
        self._semaphore.release()
        async with self._dag_count_lock:
            self._active_dag_count = max(0, self._active_dag_count - 1)

    # ── LLM call tracking per request ───────────────────────────────────

    def increment_llm_calls(self, correlation_id: str) -> int:
        """Increment and return the current LLM call count for a request."""
        self._llm_call_counts[correlation_id] = self._llm_call_counts.get(correlation_id, 0) + 1
        return self._llm_call_counts[correlation_id]

    def get_llm_call_count(self, correlation_id: str) -> int:
        """Get current LLM call count for a request."""
        return self._llm_call_counts.get(correlation_id, 0)

    def cleanup_request(self, correlation_id: str) -> None:
        """Clean up LLM call tracking for a completed request."""
        self._llm_call_counts.pop(correlation_id, None)

    # ── Monitoring ───────────────────────────────────────────────────────

    @property
    def active_dag_count(self) -> int:
        return self._active_dag_count

    @property
    def available_slots(self) -> int:
        return self._semaphore._value

    def status(self) -> dict:
        """Current guard status for monitoring/alerting."""
        return {
            "active_dags": self._active_dag_count,
            "max_active_dags": self._max_active,
            "available_slots": self.available_slots,
            "max_total_slots": self._max_active * self._max_parallel,
            "tracked_requests": len(self._llm_call_counts),
            "limits": {
                "max_dag_nodes": self.MAX_DAG_NODES,
                "max_llm_calls": self.MAX_LLM_CALLS_PER_REQUEST,
                "max_active_dags": self._max_active,
                "max_parallel_nodes": self._max_parallel,
            },
        }
