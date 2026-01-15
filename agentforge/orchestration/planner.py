"""AgentForge 编排执行层：planner。

本模块负责 planner 相关能力，是 编排执行层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：PlanResult、PlannerConfig、PlannerAgent。
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 说明：该步骤用于实现上述逻辑并保证行为稳定。

PLANNER_SYSTEM_PROMPT = """\
You are a task decomposition engine. Given a user task and a list of available
agents, produce a DAG (Directed Acyclic Graph) execution plan.

Available agents:
{agent_descriptions}

Rules:
1. Each node must reference a valid agent_name from the list above.
2. Define edges to express data dependencies (which node's output feeds into another).
3. Keep the DAG simple — prefer fewer nodes over over-decomposition.
4. Maximum {max_nodes} nodes allowed.
5. For simple tasks that a single agent can handle, return a single-node DAG.

Output STRICT JSON only (no markdown, no commentary):
{{
  "name": "descriptive_plan_name",
  "nodes": [
    {{"node_id": "step1", "agent_name": "agent_name", "description": "what this step does"}},
    ...
  ],
  "edges": [
    {{"from": "step1", "to": "step2"}},
    ...
  ],
  "rationale": "brief explanation of the plan"
}}
"""

REPLAN_SYSTEM_PROMPT = """\
You are a task re-planning engine. The previous execution plan partially failed.
Given the original task, the failed plan, and the failure details, produce a NEW
DAG plan that works around the failures.

Available agents:
{agent_descriptions}

Previous plan failed nodes: {failed_nodes}
Previous plan error: {error_detail}

Rules:
1. You may remove failed nodes, add alternative nodes, or reorder dependencies.
2. Do NOT repeat the exact same plan — something must change.
3. Keep max {max_nodes} nodes.
4. Output STRICT JSON only (same schema as before).
"""


@dataclass
class PlanResult:
    """PlanResult。

    PlanResult 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - success: bool。
    - dag_spec: Optional[dict]。
    - rationale: str。
    - error: Optional[str]。
    - fallback_single_agent: str。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    success: bool
    dag_spec: Optional[dict] = None  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    rationale: str = ""
    error: Optional[str] = None
    fallback_single_agent: str = ""  # Agent 注册与查询。


@dataclass
class PlannerConfig:
    """PlannerConfig。

    PlannerConfig 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - max_nodes: int。
    - max_replan_attempts: int。
    - model_name: str。
    - timeout_seconds: float。
    - few_shot_examples: list[dict]。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    max_nodes: int = 50  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    max_replan_attempts: int = 2  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    model_name: str = "Qwen3-Pro"  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    timeout_seconds: float = 15.0  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    few_shot_examples: list[dict] = field(default_factory=list)


class PlannerAgent:
    """PlannerAgent。

    PlannerAgent 是核心运行时组件，负责状态管理、调度和跨模块协作。

    主要成员：
    - 方法 plan()。
    - 方法 replan()。
    - 方法 build_dag()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(
        self,
        llm_gateway,  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        agent_registry,  # Agent 注册与查询。
        config: Optional[PlannerConfig] = None,
    ):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            llm_gateway: Any，调用方传入的 llm_gateway 参数。
            agent_registry: Any，调用方传入的 agent_registry 参数。
            config: Optional[PlannerConfig]，调用方传入的 config 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._llm = llm_gateway
        self._registry = agent_registry
        self._config = config or PlannerConfig()

    async def plan(self, task_description: str, context: Optional[dict] = None) -> PlanResult:
        """执行 plan 对应的逻辑，并返回处理结果。

        Args:
            task_description: str，调用方传入的 task_description 参数。
            context: Optional[dict]，调用方传入的 context 参数。

        Returns:
            PlanResult，函数执行后的结果。
        """
        agent_descriptions = self._get_agent_descriptions()
        system_prompt = PLANNER_SYSTEM_PROMPT.format(
            agent_descriptions=agent_descriptions,
            max_nodes=self._config.max_nodes,
        )

        user_prompt = f"Task: {task_description}"
        if context:
            user_prompt += f"\n\nContext:\n{json.dumps(context, ensure_ascii=False, indent=2)}"

        try:
            import asyncio

            response = await asyncio.wait_for(
                self._llm.achat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    model=self._config.model_name,
                    temperature=0.1,  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
                    max_tokens=2000,
                ),
                timeout=self._config.timeout_seconds,
            )

            dag_spec = self._parse_response(response)
            if dag_spec is None:
                logger.warning("Planner: LLM returned unparseable JSON, falling back")
                return self._fallback_plan(task_description)

            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            validation_error = self._validate_plan(dag_spec)
            if validation_error:
                logger.warning("Planner: invalid plan — %s, falling back", validation_error)
                return PlanResult(
                    success=False,
                    error=validation_error,
                    fallback_single_agent=self._guess_single_agent(task_description),
                )

            return PlanResult(
                success=True,
                dag_spec=dag_spec,
                rationale=dag_spec.get("rationale", ""),
            )

        except Exception as e:
            logger.error("Planner: planning failed — %s", str(e)[:200])
            return PlanResult(
                success=False,
                error=str(e)[:500],
                fallback_single_agent=self._guess_single_agent(task_description),
            )

    async def replan(
        self,
        original_task: str,
        failed_dag_spec: dict,
        failed_nodes: list[str],
        error_detail: str,
    ) -> PlanResult:
        """执行 replan 对应的逻辑，并返回处理结果。

        Args:
            original_task: str，调用方传入的 original_task 参数。
            failed_dag_spec: dict，调用方传入的 failed_dag_spec 参数。
            failed_nodes: list[str]，调用方传入的 failed_nodes 参数。
            error_detail: str，调用方传入的 error_detail 参数。

        Returns:
            PlanResult，函数执行后的结果。
        """
        agent_descriptions = self._get_agent_descriptions()
        system_prompt = REPLAN_SYSTEM_PROMPT.format(
            agent_descriptions=agent_descriptions,
            max_nodes=self._config.max_nodes,
            failed_nodes=", ".join(failed_nodes),
            error_detail=error_detail[:500],
        )

        user_prompt = (
            f"Original task: {original_task}\n\n"
            f"Previous plan:\n{json.dumps(failed_dag_spec, ensure_ascii=False, indent=2)}"
        )

        try:
            import asyncio

            response = await asyncio.wait_for(
                self._llm.achat(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    model=self._config.model_name,
                    temperature=0.1,
                    max_tokens=2000,
                ),
                timeout=self._config.timeout_seconds,
            )

            dag_spec = self._parse_response(response)
            if dag_spec is None:
                return PlanResult(success=False, error="Re-plan returned unparseable JSON")

            validation_error = self._validate_plan(dag_spec)
            if validation_error:
                return PlanResult(success=False, error=f"Re-plan invalid: {validation_error}")

            return PlanResult(
                success=True,
                dag_spec=dag_spec,
                rationale=dag_spec.get("rationale", "Re-plan to work around failures"),
            )

        except Exception as e:
            logger.error("Planner: re-plan failed — %s", str(e)[:200])
            return PlanResult(success=False, error=str(e)[:500])

    def build_dag(self, dag_spec: dict) -> Any:
        """构建目标对象，并返回调用方需要的结果。

        Args:
            dag_spec: dict，调用方传入的 dag_spec 参数。

        Returns:
            Any，函数执行后的结果。
        """
        from agentforge.orchestration.dag_engine import DAGGraph, DAGNode

        graph = DAGGraph(name=dag_spec.get("name", "planned_dag"))

        for node_spec in dag_spec.get("nodes", []):
            node = DAGNode(
                node_id=node_spec["node_id"],
                agent_name=node_spec["agent_name"],
                input_mapping=node_spec.get("input_mapping", {}),
                output_key=node_spec.get("output_key", node_spec["node_id"]),
            )
            graph.add_node(node)

        for edge_spec in dag_spec.get("edges", []):
            graph.add_edge(edge_spec["from"], edge_spec["to"])

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._auto_wire_inputs(graph)

        return graph

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    def _get_agent_descriptions(self) -> str:
        """执行 _get_agent_descriptions 对应的逻辑，并返回处理结果。

        Returns:
            str，函数执行后的结果。
        """
        registered = self._registry.list_agents()
        lines = []
        for name in registered:
            info = self._registry.info(name)
            desc = info.get("description", "No description")
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines) if lines else "- (no agents registered)"

    def _parse_response(self, response: Any) -> Optional[dict]:
        """执行 _parse_response 对应的逻辑，并返回处理结果。

        Args:
            response: Any，调用方传入的 response 参数。

        Returns:
            Optional[dict]，函数执行后的结果。
        """
        text = ""
        if hasattr(response, "content"):
            text = response.content
        elif isinstance(response, str):
            text = response
        elif isinstance(response, dict):
            text = response.get("content", "")

        if not text:
            return None

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            lines = [line for line in lines[1:] if line.strip() != "```"]
            text = "\n".join(lines)

        try:
            spec = json.loads(text)
            if not isinstance(spec, dict):
                return None
            return spec
        except json.JSONDecodeError:
            logger.warning("Planner: failed to parse JSON from LLM response")
            return None

    def _validate_plan(self, dag_spec: dict) -> Optional[str]:
        """执行 _validate_plan 对应的逻辑，并返回处理结果。

        Args:
            dag_spec: dict，调用方传入的 dag_spec 参数。

        Returns:
            Optional[str]，函数执行后的结果。
        """
        nodes = dag_spec.get("nodes", [])
        edges = dag_spec.get("edges", [])

        if not nodes:
            return "Plan has no nodes"
        if len(nodes) > self._config.max_nodes:
            return f"Plan has {len(nodes)} nodes, exceeds max {self._config.max_nodes}"

        node_ids = set()
        registered_agents = set(self._registry.list_agents())

        for node in nodes:
            nid = node.get("node_id")
            agent = node.get("agent_name")
            if not nid:
                return f"Node missing node_id: {node}"
            if not agent:
                return f"Node '{nid}' missing agent_name"
            if nid in node_ids:
                return f"Duplicate node_id: {nid}"
            if registered_agents and agent not in registered_agents:
                return f"Unknown agent '{agent}' in node '{nid}'"
            node_ids.add(nid)

        for edge in edges:
            src = edge.get("from")
            dst = edge.get("to")
            if src not in node_ids:
                return f"Edge references unknown source: {src}"
            if dst not in node_ids:
                return f"Edge references unknown target: {dst}"

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        in_degree = {nid: 0 for nid in node_ids}
        adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for edge in edges:
            adjacency[edge["from"]].append(edge["to"])
            in_degree[edge["to"]] += 1

        from collections import deque

        queue = deque(nid for nid, d in in_degree.items() if d == 0)
        sorted_count = 0
        while queue:
            nid = queue.popleft()
            sorted_count += 1
            for neighbor in adjacency[nid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if sorted_count != len(node_ids):
            return "Plan contains a cycle"

        return None

    def _auto_wire_inputs(self, graph: Any) -> None:
        """执行 _auto_wire_inputs 对应的逻辑，并返回处理结果。

        Args:
            graph: Any，调用方传入的 graph 参数。

        Returns:
            None，函数执行后的结果。
        """
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        incoming: dict[str, list[str]] = {nid: [] for nid in graph.nodes}
        for src, dst in graph.edges:
            incoming[dst].append(src)

        for node_id, sources in incoming.items():
            node = graph.nodes[node_id]
            if node.input_mapping:
                continue  # 就绪状态。
            if not sources:
                # 说明：该步骤用于实现上述逻辑并保证行为稳定。
                node.input_mapping = {"query": "$input.user_query"}
            elif len(sources) == 1:
                src_key = graph.nodes[sources[0]].output_key or sources[0]
                node.input_mapping = {"query": f"$ctx.{src_key}"}
            else:
                # 说明：该步骤用于实现上述逻辑并保证行为稳定。
                mapping = {"query": f"$ctx.{graph.nodes[sources[0]].output_key or sources[0]}"}
                for i, src in enumerate(sources[1:], 1):
                    src_key = graph.nodes[src].output_key or src
                    mapping[f"context_{i}"] = f"$ctx.{src_key}"
                node.input_mapping = mapping

    def _fallback_plan(self, task_description: str) -> PlanResult:
        """执行 _fallback_plan 对应的逻辑，并返回处理结果。

        Args:
            task_description: str，调用方传入的 task_description 参数。

        Returns:
            PlanResult，函数执行后的结果。
        """
        agent_name = self._guess_single_agent(task_description)
        return PlanResult(
            success=False,
            error="LLM planning failed, using single-agent fallback",
            fallback_single_agent=agent_name,
        )

    def _guess_single_agent(self, task_description: str) -> str:
        """执行 _guess_single_agent 对应的逻辑，并返回处理结果。

        Args:
            task_description: str，调用方传入的 task_description 参数。

        Returns:
            str，函数执行后的结果。
        """
        task_lower = task_description.lower()

        keyword_agent_map = [
            (["security", "vulnerability", "cve", "injection", "xss"], "security-scan"),
            (["test", "unit test", "integration test", "coverage"], "test-execution"),
            (["document", "readme", "docstring", "comment"], "doc-generator"),
            (["deploy", "release", "ci/cd", "pipeline"], "deploy"),
            (["review", "code review", "refactor", "lint"], "code-review"),
        ]

        for keywords, agent_name in keyword_agent_map:
            if any(kw in task_lower for kw in keywords):
                if agent_name in self._registry.list_agents():
                    return agent_name

        # Agent 注册与查询。
        if "code-review" in self._registry.list_agents():
            return "code-review"

        # Agent 注册与查询。
        agents = self._registry.list_agents()
        return agents[0] if agents else "unknown"
