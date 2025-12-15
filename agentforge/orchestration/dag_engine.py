"""
DAG Task Engine — orchestration layer core component.

Based on Kahn's algorithm topological sort, supports DAGs up to 50 nodes.
Independent nodes execute in parallel; dependent nodes wait serially.
Three modes: static, dynamic, and runtime re-orchestration.
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

from agentforge.core.context_store import ContextStore

logger = logging.getLogger(__name__)


@dataclass
class DAGNode:
    """
    Single node in the execution graph.

    input_mapping syntax:
        $ctx.node_output   → read from ContextStore (another node's output)
        $input.field_name  → read from the original input_data
        literal_value      → pass through as-is
    """

    node_id: str
    agent_name: str
    input_mapping: dict[str, str] = field(default_factory=dict)
    output_key: str = ""
    timeout: float = 30.0  # Per-node timeout (matches L2 agent timeout)
    retry_count: int = 2  # Max retries on failure


@dataclass
class DAGResult:
    """Result of a complete DAG execution. Partial results on timeout/early termination."""

    success: bool
    node_results: dict[str, Any] = field(default_factory=dict)
    total_cost: float = 0.0
    total_latency: float = 0.0
    success_rate: float = 1.0
    span_list: list[dict] = field(default_factory=list)
    error: Optional[str] = None
    degraded: bool = False
    terminated_early: bool = False


@dataclass
class DAGGraph:
    """
    Directed Acyclic Graph definition.
    Nodes = Agent executions, Edges = data dependencies.
    Must be acyclic — validate() checks before execution.
    """

    nodes: dict[str, DAGNode] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)
    name: str = "default_dag"

    def add_node(self, node: DAGNode) -> None:
        if node.node_id in self.nodes:
            raise ValueError(f"Duplicate node_id: {node.node_id}")
        self.nodes[node.node_id] = node

    def add_edge(self, from_id: str, to_id: str) -> None:
        if from_id not in self.nodes:
            raise ValueError(f"Source node not found: {from_id}")
        if to_id not in self.nodes:
            raise ValueError(f"Target node not found: {to_id}")
        self.edges.append((from_id, to_id))

    def validate(self) -> bool:
        """Check for cycles via topological sort."""
        try:
            self.topological_sort()
            return True
        except ValueError as e:
            logger.error("DAG validation failed: %s", e)
            return False

    def topological_sort(self) -> list[str]:
        """
        Kahn's algorithm — O(V+E). Returns node_ids in execution order.
        Adjacent nodes in result (same level) are parallelizable.
        Raises ValueError if graph contains a cycle.
        """
        in_degree = {nid: 0 for nid in self.nodes}
        adjacency: dict[str, list[str]] = {nid: [] for nid in self.nodes}
        for src, dst in self.edges:
            adjacency[src].append(dst)
            in_degree[dst] += 1

        queue = deque(nid for nid, d in in_degree.items() if d == 0)
        ordered: list[str] = []
        while queue:
            nid = queue.popleft()
            ordered.append(nid)
            for neighbor in adjacency[nid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered) != len(self.nodes):
            raise ValueError(f"Cycle detected: sorted {len(ordered)}/{len(self.nodes)}")
        return ordered


# L3 early-termination threshold: when the fraction of non-successful (failed or
# degraded) nodes among all DAG nodes exceeds this ratio, stop executing.
EARLY_TERMINATION_FAILURE_RATIO = 0.30


class DAGEngine:
    """
    Core DAG executor with parallel waves, timeout, degradation, replanning.

    Execution: nodes grouped into waves by topological level, parallel within
    wave (up to max_parallel), serial between waves. Global timeout wraps all.
    """

    def __init__(self, max_nodes: int = 50, global_timeout: float = 300.0, max_parallel: int = 5):
        self._max_nodes = max_nodes
        self._global_timeout = global_timeout
        self._max_parallel = max_parallel
        self._agent_registry = None
        self._degradation_mgr = None
        self._request_guard = None
        self._tracer = None
        self._cost_tracker = None

    def set_dependencies(
        self,
        agent_registry=None,
        degradation_mgr=None,
        request_guard=None,
        tracer=None,
        cost_tracker=None,
    ) -> None:
        self._agent_registry = agent_registry
        self._degradation_mgr = degradation_mgr
        self._request_guard = request_guard
        self._tracer = tracer
        self._cost_tracker = cost_tracker

    async def execute(
        self,
        correlation_id: str,
        input_data: dict,
        dag: Optional[DAGGraph] = None,
        agent_registry=None,
        context: Optional[ContextStore] = None,
    ) -> DAGResult:
        """
        Execute a DAG with full orchestration: parallelism, timeout, degradation.
        Returns DAGResult (partial on timeout/early termination).
        """
        start = time.monotonic()
        registry = agent_registry or self._agent_registry
        if dag is None:
            return DAGResult(success=False, error="No DAG provided")

        # Pre-flight checks
        if len(dag.nodes) > self._max_nodes:
            return DAGResult(
                success=False, error=f"DAG size {len(dag.nodes)} > max {self._max_nodes}"
            )
        if not dag.validate():
            return DAGResult(success=False, error="DAG has cycle")
        if self._request_guard and not self._request_guard.check_dag_size(len(dag.nodes)):
            return DAGResult(success=False, error="Request guard rejected DAG size")

        # Initialize context and degradation counters
        ctx = context or ContextStore()
        if not context:
            await ctx.initialize(input_data)
        if self._degradation_mgr:
            await self._degradation_mgr.reset_dag_counters()

        # Build execution structures
        in_degree = {nid: 0 for nid in dag.nodes}
        adjacency: dict[str, list[str]] = {nid: [] for nid in dag.nodes}
        for src, dst in dag.edges:
            adjacency[src].append(dst)
            in_degree[dst] += 1

        node_results: dict[str, Any] = {}
        degraded_nodes: set[str] = set()
        completed: set[str] = set()
        total_nodes = len(dag.nodes)
        span_list: list[dict] = []

        # Reserve a concurrency slot (RequestGuard dimension 3) before executing.
        # Guarded by try/finally below so the slot is always released.
        slot_acquired = False
        if self._request_guard:
            slot_acquired = await self._request_guard.acquire()
            if not slot_acquired:
                self._request_guard.cleanup_request(correlation_id)
                return DAGResult(
                    success=False,
                    error="Request guard rejected: concurrency limit reached",
                )

        # Start trace
        trace = None
        if self._tracer:
            trace = await self._tracer.start_trace(correlation_id)

        try:
            await asyncio.wait_for(
                self._run_waves(
                    dag,
                    in_degree,
                    adjacency,
                    ctx,
                    registry,
                    node_results,
                    degraded_nodes,
                    completed,
                    span_list,
                    correlation_id,
                ),
                timeout=self._global_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("DAG[%s] global timeout (%.0fs)", dag.name, self._global_timeout)
            if self._degradation_mgr:
                await self._degradation_mgr.handle_system_failure()
        except Exception as e:
            logger.error("DAG[%s] error: %s", dag.name, e)
        finally:
            # Always free the concurrency slot and clean up per-request LLM tracking.
            if self._request_guard:
                if slot_acquired:
                    await self._request_guard.release()
                self._request_guard.cleanup_request(correlation_id)

        # Compute final metrics. node_results holds only truly-successful nodes;
        # degraded/failed nodes are excluded from success_rate so the metric is honest.
        elapsed_ms = (time.monotonic() - start) * 1000
        success_rate = len(node_results) / total_nodes if total_nodes else 0.0
        total_cost = sum(r.get("cost", 0) for r in node_results.values() if isinstance(r, dict))
        failed_ratio = 1.0 - success_rate

        # L3 degradation check
        terminated_early = False
        if self._degradation_mgr:
            check = await self._degradation_mgr.handle_dag_degradation(failed_ratio, total_nodes)
            terminated_early = check.get("should_terminate", False)

        # End trace
        if self._tracer and trace:
            from agentforge.observability.tracing import SpanStatus

            status = (
                SpanStatus.OK
                if success_rate == 1.0
                else (SpanStatus.PARTIAL if success_rate > 0 else SpanStatus.ERROR)
            )
            await self._tracer.end_trace(trace, status)

        return DAGResult(
            success=success_rate > 0.7,
            node_results=node_results,
            total_cost=total_cost,
            total_latency=elapsed_ms,
            success_rate=success_rate,
            span_list=span_list,
            degraded=bool(degraded_nodes),
            terminated_early=terminated_early,
        )

    async def _run_waves(
        self,
        dag: DAGGraph,
        in_degree: dict[str, int],
        adjacency: dict[str, list[str]],
        ctx: ContextStore,
        registry: Any,
        node_results: dict[str, Any],
        degraded_nodes: set[str],
        completed: set[str],
        span_list: list[dict],
        correlation_id: str,
    ) -> None:
        """
        Execute nodes in parallel waves — each wave = nodes with all deps satisfied.

        Successfully executed nodes are recorded in ``node_results``; nodes that
        were degraded or failed are tracked separately in ``degraded_nodes`` so
        success accounting and L3 early termination reflect reality.
        """
        remaining = dict(in_degree)
        while len(completed) < len(dag.nodes):
            # Find wave: nodes with in_degree == 0 and not yet done
            wave = [nid for nid in dag.nodes if nid not in completed and remaining.get(nid, 0) == 0]
            if not wave:
                break

            # L3 degradation check before each wave: early termination when too
            # many finished nodes were not successful (failed or degraded).
            if self._degradation_mgr and len(completed) > 0:
                failed = len(completed) - len(node_results)
                ratio = failed / len(dag.nodes) if dag.nodes else 0
                if ratio > EARLY_TERMINATION_FAILURE_RATIO:
                    logger.warning("DAG early termination: %.0f%% failed", ratio * 100)
                    return

            # Execute wave nodes in parallel with semaphore
            sem = asyncio.Semaphore(self._max_parallel)

            async def _run(nid: str) -> dict:
                async with sem:
                    return await self._execute_node(
                        nid, dag, ctx, registry, span_list, correlation_id
                    )

            results = await asyncio.gather(*[_run(n) for n in wave], return_exceptions=True)

            for nid, result in zip(wave, results):
                completed.add(nid)
                out_key = dag.nodes[nid].output_key or nid
                if isinstance(result, Exception):
                    logger.error("Node[%s] failed: %s", nid, result)
                    degraded_nodes.add(nid)
                    await ctx.write(out_key, None)
                elif isinstance(result, dict) and result.get("degraded"):
                    # Degraded node — do not count toward success_rate, but do
                    # publish its (partial) output so downstream nodes can proceed.
                    degraded_nodes.add(nid)
                    await ctx.write(out_key, result.get("result"))
                else:
                    node_results[nid] = result
                    val = result.get("result", result) if isinstance(result, dict) else result
                    await ctx.write(out_key, val)
                # Decrement in-degree for downstream nodes
                for downstream in adjacency.get(nid, []):
                    remaining[downstream] -= 1

    async def _execute_node(
        self,
        node_id: str,
        dag: DAGGraph,
        ctx: ContextStore,
        registry: Any,
        span_list: list[dict],
        correlation_id: str,
    ) -> dict:
        """Execute single node with retry + L2 degradation on failure."""
        node = dag.nodes[node_id]
        agent = await registry.get(node.agent_name)
        input_data = await ctx.read_with_mapping(node.input_mapping)
        if "query" not in input_data:
            input_data["query"] = f"Execute {node_id}"

        span = None
        if self._tracer:
            from agentforge.observability.tracing import SpanType

            span = await self._tracer.start_span(
                trace=None, span_type=SpanType.AGENT, name=f"node:{node_id}"
            )

        for attempt in range(node.retry_count + 1):
            # Reserve one unit of the per-request LLM budget (RequestGuard dimension 2).
            if self._request_guard:
                current = self._request_guard.get_llm_call_count(correlation_id)
                if not self._request_guard.check_llm_call_count(current):
                    logger.warning("Node[%s] LLM call budget exhausted", node_id)
                    return {
                        "result": None,
                        "degraded": True,
                        "error": f"LLM call budget exhausted for request {correlation_id}",
                    }
                self._request_guard.increment_llm_calls(correlation_id)

            try:
                result = await asyncio.wait_for(
                    agent.run(input_data, span=span), timeout=node.timeout
                )
                if self._cost_tracker:
                    await self._cost_tracker.record(
                        token_count=result.token_usage.get("total", 0),
                        model_name=node.agent_name,
                        cost=result.cost,
                        agent_name=node.agent_name,
                    )
                if self._tracer and span:
                    from agentforge.observability.tracing import SpanStatus

                    await self._tracer.end_span(
                        span, SpanStatus.OK, {"node_id": node_id, "attempt": attempt}
                    )
                return (
                    result.data
                    if result.success
                    else {"result": None, "degraded": True, "error": result.error}
                )
            except asyncio.TimeoutError:
                logger.warning("Node[%s] attempt %d timed out", node_id, attempt + 1)
            except Exception as e:
                logger.warning("Node[%s] attempt %d failed: %s", node_id, attempt + 1, str(e)[:200])
            # L2 degradation: check if we should keep retrying
            if self._degradation_mgr and attempt < node.retry_count:
                deg = await self._degradation_mgr.handle_node_failure(
                    node_id, Exception("retry"), node.retry_count
                )
                if deg["action"] == "fallback_default":
                    break

        # All retries exhausted
        if self._tracer and span:
            from agentforge.observability.tracing import SpanStatus

            await self._tracer.end_span(span, SpanStatus.ERROR, {"node_id": node_id})
        return {
            "result": None,
            "degraded": True,
            "error": f"Node {node_id} failed after {node.retry_count} retries",
        }

    async def replan(
        self,
        current_dag: DAGGraph,
        failed_node: str,
        new_nodes: list[DAGNode],
        new_edges: list[tuple[str, str]],
    ) -> DAGGraph:
        """
        Runtime re-orchestration: modify DAG mid-execution to work around failure.
        Inserts new nodes/edges, validates no cycle, checks size limit.
        """
        new_dag = DAGGraph(
            nodes=dict(current_dag.nodes),
            edges=list(current_dag.edges),
            name=f"{current_dag.name}_replanned",
        )
        # Remove edges involving the failed node
        new_dag.edges = [(f, t) for f, t in new_dag.edges if f != failed_node and t != failed_node]
        for node in new_nodes:
            new_dag.add_node(node)
        for src, dst in new_edges:
            new_dag.add_edge(src, dst)
        if not new_dag.validate():
            raise ValueError(f"Replanned DAG has cycle — cannot work around {failed_node}")
        if len(new_dag.nodes) > self._max_nodes:
            raise ValueError(f"Replanned DAG exceeds max {self._max_nodes}")
        logger.info("DAG replanned: bypassed '%s', added %d nodes", failed_node, len(new_nodes))
        return new_dag
