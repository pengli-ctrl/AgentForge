"""AgentForge 编排执行层：dag_engine。

本模块负责 dag_engine 相关能力，是 编排执行层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：DAGNode、DAGResult、DAGGraph、DAGEngine。
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
    """DAGNode。

    DAGNode 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - node_id: str。
    - agent_name: str。
    - input_mapping: dict[str, str]。
    - output_key: str。
    - timeout: float。
    - retry_count: int。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    node_id: str
    agent_name: str
    input_mapping: dict[str, str] = field(default_factory=dict)
    output_key: str = ""
    timeout: float = 30.0  # Agent 注册与查询。
    retry_count: int = 2  # 说明：该步骤用于实现上述逻辑并保证行为稳定。


@dataclass
class DAGResult:
    """DAGResult。

    DAGResult 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - success: bool。
    - node_results: dict[str, Any]。
    - total_cost: float。
    - total_latency: float。
    - success_rate: float。
    - span_list: list[dict]。
    - error: Optional[str]。
    - degraded: bool。
    - terminated_early: bool。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

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
    """DAGGraph。

    DAGGraph 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - nodes: dict[str, DAGNode]。
    - edges: list[tuple[str, str]]。
    - name: str。
    - 方法 add_node()。
    - 方法 add_edge()。
    - 方法 validate()。
    - 方法 topological_sort()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    nodes: dict[str, DAGNode] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)
    name: str = "default_dag"

    def add_node(self, node: DAGNode) -> None:
        """执行 add_node 对应的逻辑，并返回处理结果。

        Args:
            node: DAGNode，调用方传入的 node 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if node.node_id in self.nodes:
            raise ValueError(f"Duplicate node_id: {node.node_id}")
        self.nodes[node.node_id] = node

    def add_edge(self, from_id: str, to_id: str) -> None:
        """执行 add_edge 对应的逻辑，并返回处理结果。

        Args:
            from_id: str，调用方传入的 from_id 参数。
            to_id: str，调用方传入的 to_id 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if from_id not in self.nodes:
            raise ValueError(f"Source node not found: {from_id}")
        if to_id not in self.nodes:
            raise ValueError(f"Target node not found: {to_id}")
        self.edges.append((from_id, to_id))

    def validate(self) -> bool:
        """执行 validate 对应的逻辑，并返回处理结果。

        Returns:
            bool，函数执行后的结果。
        """
        try:
            self.topological_sort()
            return True
        except ValueError as e:
            logger.error("DAG validation failed: %s", e)
            return False

    def topological_sort(self) -> list[str]:
        """执行 topological_sort 对应的逻辑，并返回处理结果。

        Returns:
            list[str]，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
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


# 失败状态。
# 说明：该步骤用于实现上述逻辑并保证行为稳定。
EARLY_TERMINATION_FAILURE_RATIO = 0.30


class DAGEngine:
    """DAGEngine。

    DAGEngine 是核心运行时组件，负责状态管理、调度和跨模块协作。

    主要成员：
    - 方法 set_dependencies()。
    - 方法 execute()。
    - 方法 replan()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(self, max_nodes: int = 50, global_timeout: float = 300.0, max_parallel: int = 5):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            max_nodes: int，调用方传入的 max_nodes 参数。
            global_timeout: float，调用方传入的 global_timeout 参数。
            max_parallel: int，调用方传入的 max_parallel 参数。

        Returns:
            None，函数执行后的结果。
        """
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
        """执行 set_dependencies 对应的逻辑，并返回处理结果。

        Args:
            agent_registry: Any，调用方传入的 agent_registry 参数。
            degradation_mgr: Any，调用方传入的 degradation_mgr 参数。
            request_guard: Any，调用方传入的 request_guard 参数。
            tracer: Any，调用方传入的 tracer 参数。
            cost_tracker: Any，调用方传入的 cost_tracker 参数。

        Returns:
            None，函数执行后的结果。
        """
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
        """执行 execute 对应的逻辑，并返回处理结果。

        Args:
            correlation_id: str，调用方传入的 correlation_id 参数。
            input_data: dict，调用方传入的 input_data 参数。
            dag: Optional[DAGGraph]，调用方传入的 dag 参数。
            agent_registry: Any，调用方传入的 agent_registry 参数。
            context: Optional[ContextStore]，调用方传入的 context 参数。

        Returns:
            DAGResult，函数执行后的结果。
        """
        start = time.monotonic()
        registry = agent_registry or self._agent_registry
        if dag is None:
            return DAGResult(success=False, error="No DAG provided")

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        if len(dag.nodes) > self._max_nodes:
            return DAGResult(
                success=False, error=f"DAG size {len(dag.nodes)} > max {self._max_nodes}"
            )
        if not dag.validate():
            return DAGResult(success=False, error="DAG has cycle")
        if self._request_guard and not self._request_guard.check_dag_size(len(dag.nodes)):
            return DAGResult(success=False, error="Request guard rejected DAG size")

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        ctx = context or ContextStore()
        if not context:
            await ctx.initialize(input_data)
        if self._degradation_mgr:
            await self._degradation_mgr.reset_dag_counters()

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
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

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        slot_acquired = False
        if self._request_guard:
            slot_acquired = await self._request_guard.acquire()
            if not slot_acquired:
                self._request_guard.cleanup_request(correlation_id)
                return DAGResult(
                    success=False,
                    error="Request guard rejected: concurrency limit reached",
                )

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
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
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            if self._request_guard:
                if slot_acquired:
                    await self._request_guard.release()
                self._request_guard.cleanup_request(correlation_id)

        # 获取结果。
        # 指标采集。
        elapsed_ms = (time.monotonic() - start) * 1000
        success_rate = len(node_results) / total_nodes if total_nodes else 0.0
        total_cost = sum(r.get("cost", 0) for r in node_results.values() if isinstance(r, dict))
        failed_ratio = 1.0 - success_rate

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        terminated_early = False
        if self._degradation_mgr:
            check = await self._degradation_mgr.handle_dag_degradation(failed_ratio, total_nodes)
            terminated_early = check.get("should_terminate", False)

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
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
        """执行 _run_waves 对应的逻辑，并返回处理结果。

        Args:
            dag: DAGGraph，调用方传入的 dag 参数。
            in_degree: dict[str, int]，调用方传入的 in_degree 参数。
            adjacency: dict[str, list[str]]，调用方传入的 adjacency 参数。
            ctx: ContextStore，调用方传入的 ctx 参数。
            registry: Any，调用方传入的 registry 参数。
            node_results: dict[str, Any]，调用方传入的 node_results 参数。
            degraded_nodes: set[str]，调用方传入的 degraded_nodes 参数。
            completed: set[str]，调用方传入的 completed 参数。
            span_list: list[dict]，调用方传入的 span_list 参数。
            correlation_id: str，调用方传入的 correlation_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        remaining = dict(in_degree)
        while len(completed) < len(dag.nodes):
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            wave = [nid for nid in dag.nodes if nid not in completed and remaining.get(nid, 0) == 0]
            if not wave:
                break

            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            # 失败状态。
            if self._degradation_mgr and len(completed) > 0:
                failed = len(completed) - len(node_results)
                ratio = failed / len(dag.nodes) if dag.nodes else 0
                if ratio > EARLY_TERMINATION_FAILURE_RATIO:
                    logger.warning("DAG early termination: %.0f%% failed", ratio * 100)
                    return

            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            sem = asyncio.Semaphore(self._max_parallel)

            async def _run(nid: str) -> dict:
                """执行 _run 对应的逻辑，并返回处理结果。

                Args:
                    nid: str，调用方传入的 nid 参数。

                Returns:
                    dict，函数执行后的结果。
                """
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
                    # 说明：该步骤用于实现上述逻辑并保证行为稳定。
                    # 说明：该步骤用于实现上述逻辑并保证行为稳定。
                    degraded_nodes.add(nid)
                    await ctx.write(out_key, result.get("result"))
                else:
                    node_results[nid] = result
                    val = result.get("result", result) if isinstance(result, dict) else result
                    await ctx.write(out_key, val)
                # 说明：该步骤用于实现上述逻辑并保证行为稳定。
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
        """执行 _execute_node 对应的逻辑，并返回处理结果。

        Args:
            node_id: str，调用方传入的 node_id 参数。
            dag: DAGGraph，调用方传入的 dag 参数。
            ctx: ContextStore，调用方传入的 ctx 参数。
            registry: Any，调用方传入的 registry 参数。
            span_list: list[dict]，调用方传入的 span_list 参数。
            correlation_id: str，调用方传入的 correlation_id 参数。

        Returns:
            dict，函数执行后的结果。
        """
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
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
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
            # 失败重试。
            if self._degradation_mgr and attempt < node.retry_count:
                deg = await self._degradation_mgr.handle_node_failure(
                    node_id, Exception("retry"), node.retry_count
                )
                if deg["action"] == "fallback_default":
                    break

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
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
        """执行 replan 对应的逻辑，并返回处理结果。

        Args:
            current_dag: DAGGraph，调用方传入的 current_dag 参数。
            failed_node: str，调用方传入的 failed_node 参数。
            new_nodes: list[DAGNode]，调用方传入的 new_nodes 参数。
            new_edges: list[tuple[str, str]]，调用方传入的 new_edges 参数。

        Returns:
            DAGGraph，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        new_dag = DAGGraph(
            nodes=dict(current_dag.nodes),
            edges=list(current_dag.edges),
            name=f"{current_dag.name}_replanned",
        )
        # 失败状态。
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
