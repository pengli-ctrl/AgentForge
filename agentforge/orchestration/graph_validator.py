"""校验 DAG 的节点、边、环和预算约束。"""

from __future__ import annotations

from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter


@dataclass(frozen=True)
class DagValidationResult:
    """校验 DAG 的节点、边、环和预算约束。

    Attributes:
        ok: 配置字段。
        order: 配置字段。
        errors: 配置字段。
    """

    ok: bool
    order: tuple[str, ...] = ()
    errors: tuple[str, ...] = field(default_factory=tuple)


class DagValidator:
    """校验节点身份、边、环和全局节点预算。"""

    def __init__(self, max_nodes: int = 50) -> None:
        """校验 DAG 的节点、边、环和预算约束。

        Args:
            max_nodes: 调用该函数所需的输入值。
        """
        self._max_nodes = max_nodes

    def validate(self, nodes: dict[str, str], edges: list[tuple[str, str]]) -> DagValidationResult:
        """校验 DAG 的节点、边、环和预算约束。

            Args:
                nodes: 调用该函数所需的输入值。
                edges: 调用该函数所需的输入值。

            Returns:
        当前操作的结构化结果。
        """
        errors: list[str] = []
        if len(nodes) > self._max_nodes:
            errors.append("max_nodes_exceeded")
        if any(not node_id or not agent for node_id, agent in nodes.items()):
            errors.append("empty_node_or_agent")
        for source, target in edges:
            if source not in nodes:
                errors.append(f"unknown_source:{source}")
            if target not in nodes:
                errors.append(f"unknown_target:{target}")
        graph: dict[str, set[str]] = {node_id: set() for node_id in nodes}
        for source, target in edges:
            if source in nodes and target in nodes:
                graph[target].add(source)
        try:
            order = tuple(TopologicalSorter(graph).static_order())
        except CycleError:
            errors.append("cycle_detected")
            order = ()
        return DagValidationResult(ok=not errors, order=order, errors=tuple(dict.fromkeys(errors)))
