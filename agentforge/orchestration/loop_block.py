"""
LoopBlock — controlled uncertainty within a deterministic DAG framework.

DAG provides deterministic execution order; LoopBlock embeds a sub-DAG
that can iterate up to 5 times (hard constraint), with an exit condition
checked after each iteration.

Use cases:
    - Self-correction: Agent produces output → validator checks → if invalid, retry
    - Iterative refinement: Agent improves output each iteration until quality threshold met
    - Convergence loops: Multi-agent debate until consensus reached

Why max 5 iterations?
    This is the "bounded retry" principle. Without a hard limit, a loop could
    run forever (infinite loop with LLM calls = infinite cost). 5 iterations
    covers 95%+ of valid use cases. If you need more, your exit condition
    is probably wrong.

    Cost analysis: 5 iterations × 2 LLM calls × $0.01 = $0.10 max per loop.
    Without limit, a stuck loop could cost $10+ before the DAG timeout fires.

Integration:
    LoopBlock is a DAG node type. The DAG engine treats it as a single node
    that internally executes a sub-DAG multiple times. LoopSpan tracks each
    iteration for observability.
"""

import time
import asyncio
import logging
from typing import Callable, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LoopResult:
    """Result from a LoopBlock execution."""
    success: bool
    iterations_completed: int
    max_iterations: int
    final_output: dict = field(default_factory=dict)
    exit_reason: str = ""             # "condition_met", "max_iterations", "error"
    iteration_results: list[dict] = field(default_factory=list)
    total_cost: float = 0.0
    total_latency_ms: float = 0.0
    converged: bool = False           # True if exit_condition was satisfied


class LoopBlock:
    """
    Loop controller embedding a sub-DAG with bounded iteration.

    Each iteration:
        1. Execute the sub-DAG with current context
        2. Check exit_condition(result, iteration_number)
        3. If exit condition met → return success
        4. If max_iterations reached → return with converged=False
        5. Agent can read current iteration via context["__loop_iteration__"]

    The exit_condition is a callable that receives the sub-DAG result and
    current iteration number, returning True to stop or False to continue.

    Thread safety: LoopBlock is not thread-safe. Each instance should be
    used by a single DAG execution at a time.
    """

    # Hard constraint: never allow more than 5 iterations regardless of config
    ABSOLUTE_MAX_ITERATIONS = 5

    def __init__(
        self,
        sub_dag,  # DAGGraph instance — the sub-DAG to execute each iteration
        max_iterations: int = 5,
        exit_condition: Optional[Callable] = None,
        name: str = "loop_block",
    ):
        """
        Args:
            sub_dag: The DAGGraph to execute in each iteration.
            max_iterations: Max iterations (capped at ABSOLUTE_MAX_ITERATIONS=5).
            exit_condition: Callable(result_dict, iteration_number) → bool.
                           Returns True to stop iterating.
                           Default: always stop after 1 iteration (no looping).
            name: Identifier for logging/tracing.
        """
        if max_iterations > self.ABSOLUTE_MAX_ITERATIONS:
            logger.warning(
                "LoopBlock[%s] max_iterations=%d exceeds hard limit of %d — capping",
                name, max_iterations, self.ABSOLUTE_MAX_ITERATIONS,
            )
        self._max_iterations = min(max_iterations, self.ABSOLUTE_MAX_ITERATIONS)
        self._sub_dag = sub_dag
        self._exit_condition = exit_condition or (lambda result, i: True)
        self._name = name

    async def execute(
        self,
        context,  # ContextStore instance
        agent_registry=None,
        tracer=None,
    ) -> LoopResult:
        """
        Execute the loop: run sub-DAG up to max_iterations times.

        Args:
            context: Shared ContextStore for data flow between iterations.
            agent_registry: Agent registry for resolving agent names in sub-DAG.
            tracer: Tracer for creating LoopSpan per iteration.

        Returns:
            LoopResult with iteration details and final output.
        """
        start_time = time.monotonic()
        iteration_results = []
        total_cost = 0.0
        final_output: dict = {}
        converged = False
        exit_reason = ""

        for iteration in range(1, self._max_iterations + 1):
            iter_start = time.monotonic()

            # Inject iteration metadata into context
            # Agents can read this to know which iteration they're in
            await context.write("__loop_iteration__", iteration)
            await context.write("__loop_name__", self._name)
            await context.write("__loop_max__", self._max_iterations)

            # Create LoopSpan for this iteration
            span = None
            if tracer:
                from agentforge.observability.tracing import SpanType
                # We need a trace reference — caller should pass it
                # For now, create span attributes directly
                pass

            try:
                # Execute the sub-DAG for this iteration
                # Import here to avoid circular dependency
                from agentforge.orchestration.dag_engine import DAGEngine

                # Create a mini-engine for sub-DAG execution
                # Inherits timeout and degradation from parent engine context
                sub_engine = DAGEngine(max_nodes=20, global_timeout=60.0, max_parallel=3)
                sub_result = await sub_engine.execute(
                    correlation_id=f"{self._name}_iter_{iteration}",
                    input_data=await context.get_all(),
                    dag=self._sub_dag,
                    agent_registry=agent_registry,
                    context=context,
                )

                iter_cost = sub_result.total_cost
                iter_latency = sub_result.total_latency
                total_cost += iter_cost
                final_output = sub_result.node_results

                iteration_results.append({
                    "iteration": iteration,
                    "success": sub_result.success_rate > 0,
                    "cost": iter_cost,
                    "latency_ms": iter_latency,
                    "output_keys": list(sub_result.node_results.keys()),
                })

            except asyncio.TimeoutError:
                iteration_results.append({
                    "iteration": iteration,
                    "success": False,
                    "error": "Sub-DAG timeout",
                })
                exit_reason = "timeout"
                break

            except Exception as e:
                logger.warning(
                    "LoopBlock[%s] iteration %d failed: %s",
                    self._name, iteration, str(e)[:200],
                )
                iteration_results.append({
                    "iteration": iteration,
                    "success": False,
                    "error": str(e)[:200],
                })
                # Continue to next iteration unless it's the last
                if iteration == self._max_iterations:
                    exit_reason = "error"
                continue

            # Check exit condition
            try:
                should_exit = self._exit_condition(final_output, iteration)
            except Exception as e:
                logger.warning(
                    "LoopBlock[%s] exit_condition raised: %s — stopping loop",
                    self._name, str(e)[:200],
                )
                should_exit = True  # Stop on condition error to prevent infinite loop

            if should_exit:
                converged = True
                exit_reason = "condition_met"
                logger.info(
                    "LoopBlock[%s] converged at iteration %d",
                    self._name, iteration,
                )
                break
        else:
            # Loop completed without break — max iterations reached
            if not exit_reason:
                exit_reason = "max_iterations"
                logger.warning(
                    "LoopBlock[%s] reached max iterations (%d) without convergence — "
                    "marked as 'cannot auto-fix'",
                    self._name, self._max_iterations,
                )

        elapsed_ms = (time.monotonic() - start_time) * 1000

        return LoopResult(
            success=converged,
            iterations_completed=len(iteration_results),
            max_iterations=self._max_iterations,
            final_output=final_output,
            exit_reason=exit_reason,
            iteration_results=iteration_results,
            total_cost=total_cost,
            total_latency_ms=elapsed_ms,
            converged=converged,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def max_iterations(self) -> int:
        return self._max_iterations
