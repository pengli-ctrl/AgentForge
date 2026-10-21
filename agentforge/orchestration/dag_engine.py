"""DAG引擎模块。"""

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
    """DAG 节点相关组件。

    Attributes:
        node_id: 节点ID。
        agent_name: 智能体名称。
        input_mapping: 输入。
        output_key: 输出键。
        timeout: 操作超时时间。
        retry_count: 重试数量。
    """

    node_id: str
    agent_name: str
    input_mapping: dict[str, str] = field(default_factory=dict)
    output_key: str = ""
    timeout: float = 30.0
    retry_count: int = 2


@dataclass
class DAGResult:
    """DAG 结果相关组件。

    Attributes:
        success: 是否成功。
        node_results: 结果。
        total_cost: 总计成本。
        total_latency: 总计。
        success_rate: 成功速率。
        span_list: 链路片段查询。
        error: 错误信息。
        degraded: 是否降级。
        terminated_early: 字段值。
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
    """DAG 图相关组件。

    Attributes:
        nodes: 字段值。
        edges: 字段值。
        name: 名称。
    """

    nodes: dict[str, DAGNode] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)
    name: str = "default_dag"

    def add_node(self, node: DAGNode) -> None:
        """添加节点。

        Args:
            node: 待处理节点。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if node.node_id in self.nodes:
            raise ValueError(f"Duplicate node_id: {node.node_id}")
        self.nodes[node.node_id] = node

    def add_edge(self, from_id: str, to_id: str) -> None:
        """添加DAG 图。

        Args:
            from_id: 从 ID。
            to_id: 到 ID。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if from_id not in self.nodes:
            raise ValueError(f"Source node not found: {from_id}")
        if to_id not in self.nodes:
            raise ValueError(f"Target node not found: {to_id}")
        self.edges.append((from_id, to_id))

    def validate(self) -> bool:
        """校验DAG 图。

        Returns:
            操作是否成功。
        """
        try:
            self.topological_sort()
            return True
        except ValueError as e:
            logger.error("DAG validation failed: %s", e)
            return False

    def topological_sort(self) -> list[str]:
        """对 DAG 节点进行拓扑排序。

        Returns:
            结果列表。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
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
EARLY_TERMINATION_FAILURE_RATIO = 0.30


class DAGEngine:
    """DAG 引擎相关组件。"""

    def __init__(self, max_nodes: int = 50, global_timeout: float = 300.0, max_parallel: int = 5):
        """初始化 DAGEngine。

        Args:
            max_nodes: 最大。
            global_timeout: 全局超时。
            max_parallel: 最大。
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
        """设置依赖。

        Args:
            agent_registry: 智能体注册表。
            degradation_mgr: 降级。
            request_guard: 请求。
            tracer: 追踪器。
            cost_tracker: 成本。
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
        """执行 DAG 调度并返回聚合结果。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。
            input_data: 输入数据。
            dag: DAG。
            agent_registry: 智能体注册表。
            context: 执行上下文。

        Returns:
            DAG 结果结果。
        """
        start = time.monotonic()
        registry = agent_registry or self._agent_registry
        if dag is None:
            return DAGResult(success=False, error="No DAG provided")

        if len(dag.nodes) > self._max_nodes:
            return DAGResult(
                success=False, error=f"DAG size {len(dag.nodes)} > max {self._max_nodes}"
            )
        if not dag.validate():
            return DAGResult(success=False, error="DAG has cycle")
        if self._request_guard and not self._request_guard.check_dag_size(len(dag.nodes)):
            return DAGResult(success=False, error="Request guard rejected DAG size")

        ctx = context or ContextStore()
        if not context:
            await ctx.initialize(input_data)
        if self._degradation_mgr:
            await self._degradation_mgr.reset_dag_counters()

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

        slot_acquired = False
        if self._request_guard:
            slot_acquired = await self._request_guard.acquire()
            if not slot_acquired:
                self._request_guard.cleanup_request(correlation_id)
                return DAGResult(
                    success=False,
                    error="Request guard rejected: concurrency limit reached",
                )

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

        terminated_early = False
        if self._degradation_mgr:
            check = await self._degradation_mgr.handle_dag_degradation(failed_ratio, total_nodes)
            terminated_early = check.get("should_terminate", False)

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
        """运行DAG 引擎。

        Args:
            dag: DAG。
            in_degree: 在。
            adjacency: 输入参数。
            ctx: 执行上下文。
            registry: 注册表实例。
            node_results: 结果。
            degraded_nodes: 已降级。
            completed: 已完成。
            span_list: 链路片段查询。
            correlation_id: 用于关联同一业务链路的关联 ID。
        """
        remaining = dict(in_degree)
        while len(completed) < len(dag.nodes):
            wave = [nid for nid in dag.nodes if nid not in completed and remaining.get(nid, 0) == 0]
            if not wave:
                break

            # 失败状态。
            if self._degradation_mgr and len(completed) > 0:
                failed = len(completed) - len(node_results)
                ratio = failed / len(dag.nodes) if dag.nodes else 0
                if ratio > EARLY_TERMINATION_FAILURE_RATIO:
                    logger.warning("DAG early termination: %.0f%% failed", ratio * 100)
                    return

            sem = asyncio.Semaphore(self._max_parallel)

            async def _run(nid: str) -> dict:
                """在并行调度并发限制下执行一个 DAG 节点。"""
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
                    degraded_nodes.add(nid)
                    await ctx.write(out_key, result.get("result"))
                else:
                    node_results[nid] = result
                    val = result.get("result", result) if isinstance(result, dict) else result
                    await ctx.write(out_key, val)
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
        """执行单个 DAG 节点并返回节点结果。

        Args:
            node_id: 节点 ID。
            dag: DAG。
            ctx: 执行上下文。
            registry: 注册表实例。
            span_list: 链路片段查询。
            correlation_id: 用于关联同一业务链路的关联 ID。

        Returns:
            结构化结果字典。
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
        """根据最新状态重新生成执行计划。

        Args:
            current_dag: DAG。
            failed_node: 失败。
            new_nodes: 输入参数。
            new_edges: 输入参数。

        Returns:
            DAG 图结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
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
