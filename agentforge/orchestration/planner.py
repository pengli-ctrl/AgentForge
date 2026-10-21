"""规划器模块。"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


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
    """套餐结果领域组件。

    Attributes:
        success: 是否成功。
        dag_spec: DAG规格。
        rationale: 字段值。
        error: 错误信息。
        fallback_single_agent: 单个智能体。
    """

    success: bool
    dag_spec: Optional[dict] = None
    rationale: str = ""
    error: Optional[str] = None
    fallback_single_agent: str = ""


@dataclass
class PlannerConfig:
    """规划器配置模型。

    Attributes:
        max_nodes: 最大。
        max_replan_attempts: 最大重新规划。
        model_name: 模型名称。
        timeout_seconds: 超时。
        few_shot_examples: 字段值。
    """

    max_nodes: int = 50
    max_replan_attempts: int = 2
    model_name: str = "Qwen3-Pro"
    timeout_seconds: float = 15.0
    few_shot_examples: list[dict] = field(default_factory=list)


class PlannerAgent:
    """规划器智能体相关组件。"""

    def __init__(
        self,
        llm_gateway,
        agent_registry,
        config: Optional[PlannerConfig] = None,
    ):
        """初始化 PlannerAgent。

        Args:
            llm_gateway: LLM 网关实例。
            agent_registry: 智能体注册表。
            config: 组件配置。
        """
        self._llm = llm_gateway
        self._registry = agent_registry
        self._config = config or PlannerConfig()

    async def plan(self, task_description: str, context: Optional[dict] = None) -> PlanResult:
        """执行套餐。

        Args:
            task_description: 任务。
            context: 执行上下文。

        Returns:
            计划结果结果。
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
                    temperature=0.1,
                    max_tokens=2000,
                ),
                timeout=self._config.timeout_seconds,
            )

            dag_spec = self._parse_response(response)
            if dag_spec is None:
                logger.warning("Planner: LLM returned unparseable JSON, falling back")
                return self._fallback_plan(task_description)

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
        """根据最新状态重新生成执行计划。

        Args:
            original_task: 任务。
            failed_dag_spec: 失败DAG规格。
            failed_nodes: 失败。
            error_detail: 错误详情。

        Returns:
            计划结果结果。
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
        """构建DAG。

        Args:
            dag_spec: DAG规格。

        Returns:
            处理结果对象。
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

        self._auto_wire_inputs(graph)

        return graph

    def _get_agent_descriptions(self) -> str:
        """获取智能体描述。

        Returns:
            字符串结果。
        """
        registered = self._registry.list_agents()
        lines = []
        for name in registered:
            info = self._registry.info(name)
            desc = info.get("description", "No description")
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines) if lines else "- (no agents registered)"

    def _parse_response(self, response: Any) -> Optional[dict]:
        """解析响应。

        Args:
            response: 响应。

        Returns:
            处理结果对象。
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

        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
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
        """校验套餐。

        Args:
            dag_spec: DAG规格。

        Returns:
            处理结果对象。
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
        """自动连接任务节点所需的输入。

        Args:
            graph: 输入参数。
        """
        incoming: dict[str, list[str]] = {nid: [] for nid in graph.nodes}
        for src, dst in graph.edges:
            incoming[dst].append(src)

        for node_id, sources in incoming.items():
            node = graph.nodes[node_id]
            if node.input_mapping:
                continue
            if not sources:
                node.input_mapping = {"query": "$input.user_query"}
            elif len(sources) == 1:
                src_key = graph.nodes[sources[0]].output_key or sources[0]
                node.input_mapping = {"query": f"$ctx.{src_key}"}
            else:
                mapping = {"query": f"$ctx.{graph.nodes[sources[0]].output_key or sources[0]}"}
                for i, src in enumerate(sources[1:], 1):
                    src_key = graph.nodes[src].output_key or src
                    mapping[f"context_{i}"] = f"$ctx.{src_key}"
                node.input_mapping = mapping

    def _fallback_plan(self, task_description: str) -> PlanResult:
        """在规划失败时构造回退计划。

        Args:
            task_description: 任务。

        Returns:
            计划结果结果。
        """
        agent_name = self._guess_single_agent(task_description)
        return PlanResult(
            success=False,
            error="LLM planning failed, using single-agent fallback",
            fallback_single_agent=agent_name,
        )

    def _guess_single_agent(self, task_description: str) -> str:
        """为简单任务推断合适的单个智能体。

        Args:
            task_description: 任务。

        Returns:
            字符串结果。
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

        if "code-review" in self._registry.list_agents():
            return "code-review"

        agents = self._registry.list_agents()
        return agents[0] if agents else "unknown"
