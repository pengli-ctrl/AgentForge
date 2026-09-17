"""
Planner Agent — automatic task decomposition engine.

The Planner is the intelligence behind "dynamic orchestration" mode:
it analyzes a natural-language task description and produces a DAGGraph
that the DAGEngine can execute.

Design philosophy:
    1. LLM only does PLANNING (decompose + order), not execution.
    2. Planner produces a structured DAGGraph — deterministic code executes it.
    3. If LLM produces an invalid DAG (cycle, unknown agent), fall back to
       static编排 (single-agent passthrough).
    4. Planner supports "re-plan" — given a failed DAG result, adjust the
       plan and return a new DAGGraph for runtime re-orchestration.

Prompt engineering notes:
    - We tell the LLM about available agents via get_available_agents().
    - We constrain output to strict JSON schema (node_id, agent_name, edges).
    - We include max_nodes limit in prompt so LLM won't over-decompose.
    - We provide 2-3 few-shot examples for common task patterns.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Planner prompt templates ────────────────────────────────────────────────

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
    """Result of a planning operation."""

    success: bool
    dag_spec: Optional[dict] = None  # Raw JSON from LLM
    rationale: str = ""
    error: Optional[str] = None
    fallback_single_agent: str = ""  # If plan fails, which single agent to use


@dataclass
class PlannerConfig:
    """Configuration for the Planner Agent."""

    max_nodes: int = 50  # Must match DAGEngine max_nodes
    max_replan_attempts: int = 2  # Max re-plan tries before giving up
    model_name: str = "Qwen3-Pro"  # Planner uses the best model
    timeout_seconds: float = 15.0  # Planning itself should be fast
    few_shot_examples: list[dict] = field(default_factory=list)


class PlannerAgent:
    """
    Automatic task decomposition agent.

    Uses LLM to convert natural-language task descriptions into DAGGraph
    execution plans. Falls back to single-agent passthrough on failure.

    Usage:
        planner = PlannerAgent(llm_gateway, agent_registry)
        result = await planner.plan("Review my Python code for security issues")
        if result.success:
            dag = planner.build_dag(result.dag_spec)
            dag_result = await dag_engine.execute(correlation_id, input_data, dag=dag)
    """

    def __init__(
        self,
        llm_gateway,  # LLMGateway instance for LLM calls
        agent_registry,  # AgentRegistry to look up available agents
        config: Optional[PlannerConfig] = None,
    ):
        self._llm = llm_gateway
        self._registry = agent_registry
        self._config = config or PlannerConfig()

    async def plan(self, task_description: str, context: Optional[dict] = None) -> PlanResult:
        """
        Decompose a task into a DAG execution plan.

        Args:
            task_description: Natural-language description of the task.
            context: Optional additional context (e.g., file contents, previous results).

        Returns:
            PlanResult with the DAG specification or fallback info.
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
                    temperature=0.1,  # Low temperature for structured output
                    max_tokens=2000,
                ),
                timeout=self._config.timeout_seconds,
            )

            dag_spec = self._parse_response(response)
            if dag_spec is None:
                logger.warning("Planner: LLM returned unparseable JSON, falling back")
                return self._fallback_plan(task_description)

            # Validate the plan
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
        """
        Re-plan after partial DAG failure.

        Args:
            original_task: The original task description.
            failed_dag_spec: The DAG spec that partially failed.
            failed_nodes: List of node_ids that failed.
            error_detail: Error message from the failed execution.

        Returns:
            PlanResult with a new DAG specification.
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
        """
        Convert a planner DAG spec (JSON dict) into a DAGGraph object.

        This creates the proper DAGGraph with DAGNode instances that
        the DAGEngine can execute.
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

        # Auto-wire input_mapping for nodes that have incoming edges but no mapping
        self._auto_wire_inputs(graph)

        return graph

    # ── Internal helpers ────────────────────────────────────────────────────

    def _get_agent_descriptions(self) -> str:
        """Build agent description list from registry for the LLM prompt."""
        registered = self._registry.list_agents()
        lines = []
        for name in registered:
            info = self._registry.info(name)
            desc = info.get("description", "No description")
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines) if lines else "- (no agents registered)"

    def _parse_response(self, response: Any) -> Optional[dict]:
        """Parse LLM response into a DAG spec dict. Returns None on failure."""
        text = ""
        if hasattr(response, "content"):
            text = response.content
        elif isinstance(response, str):
            text = response
        elif isinstance(response, dict):
            text = response.get("content", "")

        if not text:
            return None

        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (```json and ```)
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
        """
        Validate a planner DAG spec. Returns error message or None if valid.
        Checks: nodes exist, agent_names are registered, edges reference valid nodes,
        no cycles, within max_nodes limit.
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

        # Cycle check via topological sort
        in_degree = {nid: 0 for nid in node_ids}
        adjacency = {nid: [] for nid in node_ids}
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
        """
        For nodes with incoming edges but no input_mapping, auto-wire:
        - If exactly one incoming edge: map "query" → "$ctx.{source_output_key}"
        - If multiple incoming edges: map "query" → "$ctx.{source_output_key}" for first,
          add additional sources as "context_N"
        """
        # Build reverse adjacency (who points to me)
        incoming: dict[str, list[str]] = {nid: [] for nid in graph.nodes}
        for src, dst in graph.edges:
            incoming[dst].append(src)

        for node_id, sources in incoming.items():
            node = graph.nodes[node_id]
            if node.input_mapping:
                continue  # Already has explicit mapping
            if not sources:
                # Root node: takes original input
                node.input_mapping = {"query": "$input.user_query"}
            elif len(sources) == 1:
                src_key = graph.nodes[sources[0]].output_key or sources[0]
                node.input_mapping = {"query": f"$ctx.{src_key}"}
            else:
                # Multiple inputs: combine
                mapping = {"query": f"$ctx.{graph.nodes[sources[0]].output_key or sources[0]}"}
                for i, src in enumerate(sources[1:], 1):
                    src_key = graph.nodes[src].output_key or src
                    mapping[f"context_{i}"] = f"$ctx.{src_key}"
                node.input_mapping = mapping

    def _fallback_plan(self, task_description: str) -> PlanResult:
        """
        Create a single-agent fallback plan when LLM planning fails.
        Guesses the best agent for the task based on keywords.
        """
        agent_name = self._guess_single_agent(task_description)
        return PlanResult(
            success=False,
            error="LLM planning failed, using single-agent fallback",
            fallback_single_agent=agent_name,
        )

    def _guess_single_agent(self, task_description: str) -> str:
        """
        Heuristic agent selection based on task description keywords.
        Used as fallback when LLM planning fails.
        """
        task_lower = task_description.lower()

        keyword_agent_map = [
            (["security", "vulnerability", "cve", "injection", "xss"], "security_scan"),
            (["test", "unit test", "integration test", "coverage"], "test_execution"),
            (["document", "readme", "docstring", "comment"], "doc_generator"),
            (["deploy", "release", "ci/cd", "pipeline"], "deploy"),
            (["review", "code review", "refactor", "lint"], "code_review"),
        ]

        for keywords, agent_name in keyword_agent_map:
            if any(kw in task_lower for kw in keywords):
                if agent_name in self._registry.list_agents():
                    return agent_name

        # Default to code_review as the most general-purpose agent
        if "code_review" in self._registry.list_agents():
            return "code_review"

        # Ultimate fallback: return first available agent
        agents = self._registry.list_agents()
        return agents[0] if agents else "unknown"
