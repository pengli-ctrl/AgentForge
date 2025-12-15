"""
Four-level degradation strategy — always produce a partial useful result, never crash.

    L1 Model:   Main model fails → fallback model → lightest model → preset response
    L2 Node:    Node fails → retry 2x → use fallback default → mark as degraded
    L3 DAG:     >30% nodes fail → early termination, return partial results
    L4 System:  Cascading failure → global degradation + P0 alert

Design rationale:
    "Partial useful result > no result" is the core principle. In a multi-agent
    system, some nodes may succeed while others fail. Rather than failing the
    entire request, we return what we have. This is especially important for
    DAGs where early nodes produce valuable intermediate results even if
    downstream nodes fail.

    Each level has its own Span type for observability. Degradation events
    are always logged as warnings (not errors) — they're expected behavior
    in a system that handles uncertainty.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# L1 circuit-breaker tuning — named constants instead of magic numbers.
CIRCUIT_WINDOW_CALLS = 10  # Look back over the last N LLM calls per model
CIRCUIT_FAILURE_THRESHOLD = 0.5  # Open the circuit when failure_rate > 0.5 (>50%)
CIRCUIT_OPEN_DURATION_SECONDS = 900  # Keep the circuit open for 15 minutes
MAX_TRACKED_OUTCOMES = 20  # Max per-model call outcomes kept in memory


class DegradationLevel(Enum):
    """Four degradation levels, from least to most severe."""

    L1_MODEL = 1  # Single model failure — switch to another model
    L2_NODE = 2  # Single node failure — retry or use fallback
    L3_DAG = 3  # Multiple node failures — early termination
    L4_SYSTEM = 4  # Cascading failure — global degradation


@dataclass
class DegradationEvent:
    """Record of a degradation event for observability."""

    level: DegradationLevel
    timestamp: float
    description: str
    action_taken: str
    affected_component: str
    span_attributes: dict = field(default_factory=dict)


class DegradationManager:
    """
    Manages degradation decisions across all four levels.

    State tracking:
    - Per-model call outcomes for circuit breaker (L1)
    - Per-node retry counts (L2)
    - Global failure ratio for DAG-level decisions (L3)
    - System-wide health for cascade detection (L4)

    Thread safety: uses asyncio.Lock for concurrent node executions
    that may trigger degradation simultaneously.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        # L1: per-model call outcomes (True=success, False=failure) for circuit breaker
        self._model_calls: dict[str, list[bool]] = {}  # model → [outcome, ...]
        self._model_circuit_open: dict[str, float] = {}  # model → open_until_timestamp
        # L2: per-node retry tracking
        self._node_retry_counts: dict[str, int] = {}
        # L3: DAG-level tracking
        self._current_dag_failures: int = 0
        self._current_dag_total: int = 0
        # L4: system health
        self._system_degraded: bool = False
        # Event log
        self._events: list[DegradationEvent] = []

    # ── L1: Model-level degradation ─────────────────────────────────────

    async def handle_llm_failure(self, model_name: str, error: Exception) -> dict:
        """
        L1 degradation: single model failure.

        Fallback chain: main_model → backup_model → lightest_model → preset_response.
        Circuit breaker: if a model has >50% failure rate over the last
        :data:`CIRCUIT_WINDOW_CALLS` calls, open the circuit for 15 minutes
        (skip it entirely). Callers should report successful calls via
        :meth:`record_llm_success` so the rate is accurate.

        Args:
            model_name: The model that failed.
            error: The exception that occurred.

        Returns:
            Dict with 'fallback_model' and 'action' describing what to do next.
        """
        async with self._lock:
            now = time.time()
            self._record_outcome_locked(model_name, False)
            self._maybe_open_circuit(model_name, now)

        # Determine fallback
        fallback_chain = self._get_fallback_chain(model_name)
        fallback_model = fallback_chain[0] if fallback_chain else None

        event = DegradationEvent(
            level=DegradationLevel.L1_MODEL,
            timestamp=now,
            description=f"Model '{model_name}' failed: {str(error)[:100]}",
            action_taken=f"Fallback to '{fallback_model}'" if fallback_model else "Preset response",
            affected_component=model_name,
            span_attributes={"fallback_model": fallback_model, "error": str(error)[:200]},
        )
        self._events.append(event)

        return {
            "fallback_model": fallback_model,
            "action": "retry_with_fallback" if fallback_model else "preset_response",
            "degraded": True,
        }

    async def record_llm_success(self, model_name: str) -> None:
        """
        Record a successful LLM call for circuit-breaker accounting.

        Call this on every successful completion so the failure-rate check in
        :meth:`handle_llm_failure` reflects the true ratio of the last
        :data:`CIRCUIT_WINDOW_CALLS` calls.
        """
        async with self._lock:
            self._record_outcome_locked(model_name, True)

    def _record_outcome_locked(self, model_name: str, success: bool) -> None:
        """Record a call outcome (True=success, False=failure), bounded in size."""
        outcomes = self._model_calls.setdefault(model_name, [])
        outcomes.append(success)
        if len(outcomes) > MAX_TRACKED_OUTCOMES:
            del outcomes[:-MAX_TRACKED_OUTCOMES]

    def _maybe_open_circuit(self, model_name: str, now: float) -> None:
        """Open the circuit when the recent failure rate exceeds the threshold."""
        recent = self._model_calls.get(model_name, [])[-CIRCUIT_WINDOW_CALLS:]
        if len(recent) < CIRCUIT_WINDOW_CALLS:
            return
        failures = sum(1 for ok in recent if not ok)
        failure_rate = failures / len(recent)
        if failure_rate > CIRCUIT_FAILURE_THRESHOLD:
            self._model_circuit_open[model_name] = now + CIRCUIT_OPEN_DURATION_SECONDS
            logger.warning(
                "Circuit breaker OPEN for model: %s (%.0f%% failures over last %d calls)",
                model_name,
                failure_rate * 100,
                CIRCUIT_WINDOW_CALLS,
            )

    def _get_fallback_chain(self, failed_model: str) -> list[str]:
        """Return ordered list of fallback models (excluding circuit-broken ones)."""
        # Priority order based on capability/cost balance
        all_models = ["Qwen3-Pro", "GLM-5", "DeepSeek-V3", "Kimi", "MiniMax"]
        now = time.time()
        available = [
            m for m in all_models if m != failed_model and self._model_circuit_open.get(m, 0) < now
        ]
        return available

    # ── L2: Node-level degradation ──────────────────────────────────────

    async def handle_node_failure(
        self,
        node_id: str,
        error: Exception,
        retry_count: int = 2,
    ) -> dict:
        """
        L2 degradation: single DAG node failure.

        Strategy: retry up to retry_count times → use fallback default → mark degraded.

        Args:
            node_id: The failed node identifier.
            error: The exception that occurred.
            retry_count: Max retries before giving up.

        Returns:
            Dict with 'action' (retry/fallback/mark_degraded) and 'retry_remaining'.
        """
        async with self._lock:
            current_retries = self._node_retry_counts.get(node_id, 0)

            if current_retries < retry_count:
                # Still have retries left
                self._node_retry_counts[node_id] = current_retries + 1
                remaining = retry_count - current_retries - 1
                action = "retry"
                logger.info(
                    "Node[%s] failed, retrying (%d remaining): %s",
                    node_id,
                    remaining,
                    str(error)[:100],
                )
            else:
                # Exhausted retries — use fallback or mark degraded
                action = "fallback_default"
                logger.warning(
                    "Node[%s] exhausted retries (%d/%d), using fallback: %s",
                    node_id,
                    current_retries,
                    retry_count,
                    str(error)[:100],
                )

        event = DegradationEvent(
            level=DegradationLevel.L2_NODE,
            timestamp=time.time(),
            description=f"Node '{node_id}' failed after {current_retries} retries",
            action_taken=action,
            affected_component=node_id,
            span_attributes={"retry_count": current_retries, "error": str(error)[:200]},
        )
        self._events.append(event)

        return {
            "action": action,
            "retry_remaining": max(0, retry_count - current_retries - 1),
            "degraded": action == "fallback_default",
            "fallback_value": self._get_node_fallback(node_id),
        }

    def _get_node_fallback(self, node_id: str) -> Any:
        """Return a safe default value for a failed node."""
        return {
            "result": None,
            "degraded": True,
            "fallback_reason": f"Node '{node_id}' failed after all retries",
        }

    # ── L3: DAG-level degradation ───────────────────────────────────────

    async def handle_dag_degradation(
        self,
        failed_ratio: float,
        total_nodes: int,
    ) -> dict:
        """
        L3 degradation: too many node failures in a single DAG.

        Triggered when failed_ratio > 0.30 (30%). Strategy: early termination —
        stop executing remaining nodes and return partial results from
        successfully completed nodes.

        Args:
            failed_ratio: Fraction of nodes that have failed (0.0 to 1.0).
            total_nodes: Total number of nodes in the DAG.

        Returns:
            Dict with 'action' (continue/terminate) and 'status'.
        """
        async with self._lock:
            self._current_dag_failures = int(failed_ratio * total_nodes)
            self._current_dag_total = total_nodes

        threshold = 0.30
        if failed_ratio > threshold:
            action = "terminate"
            logger.warning(
                "DAG degradation: %.0f%% nodes failed (%d/%d) > %.0f%% threshold — "
                "early termination triggered",
                failed_ratio * 100,
                self._current_dag_failures,
                total_nodes,
                threshold * 100,
            )
        else:
            action = "continue"

        event = DegradationEvent(
            level=DegradationLevel.L3_DAG,
            timestamp=time.time(),
            description=(
                f"DAG failure ratio: {failed_ratio:.1%} "
                f"({self._current_dag_failures}/{total_nodes})"
            ),
            action_taken=action,
            affected_component="dag",
            span_attributes={"failed_ratio": failed_ratio, "total_nodes": total_nodes},
        )
        self._events.append(event)

        return {
            "action": action,
            "failed_count": self._current_dag_failures,
            "success_count": total_nodes - self._current_dag_failures,
            "should_terminate": failed_ratio > threshold,
        }

    # ── L4: System-level degradation ────────────────────────────────────

    async def handle_system_failure(self) -> dict:
        """
        L4 degradation: cascading system-wide failure.

        Triggered when multiple DAGs are failing simultaneously or the
        degradation rate is unsustainable. Strategy: global degradation
        mode + P0 alert.

        In degraded mode:
        - All new requests get preset responses immediately
        - Running DAGs are cancelled
        - P0 alert sent to on-call
        """
        async with self._lock:
            self._system_degraded = True

        event = DegradationEvent(
            level=DegradationLevel.L4_SYSTEM,
            timestamp=time.time(),
            description="System-wide cascading failure detected",
            action_taken="Global degradation mode + P0 alert",
            affected_component="system",
        )
        self._events.append(event)

        logger.critical(
            "P0 ALERT: System entering global degradation mode. "
            "All DAGs cancelled, preset responses enabled."
        )

        return {
            "action": "global_degradation",
            "p0_alert": True,
            "accept_new_requests": False,
            "preset_response": {
                "result": "Service temporarily degraded. Please retry later.",
                "degraded": True,
            },
        }

    # ── Utilities ────────────────────────────────────────────────────────

    async def reset_dag_counters(self) -> None:
        """Reset per-DAG counters. Called at start of each DAG execution."""
        async with self._lock:
            self._current_dag_failures = 0
            self._current_dag_total = 0
            self._node_retry_counts.clear()

    async def recover_system(self) -> None:
        """Exit global degradation mode. Called after system recovery."""
        async with self._lock:
            self._system_degraded = False
            self._model_circuit_open.clear()
            self._model_calls.clear()
        logger.info("System recovered from global degradation mode")

    @property
    def is_system_degraded(self) -> bool:
        return self._system_degraded

    def get_recent_events(self, count: int = 50) -> list[DegradationEvent]:
        """Get most recent degradation events for debugging."""
        return self._events[-count:]
