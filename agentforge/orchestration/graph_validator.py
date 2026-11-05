"""Deterministic DAG validation for the Temporal execution path."""

from __future__ import annotations

from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter


@dataclass(frozen=True)
class DagValidationResult:
    ok: bool
    order: tuple[str, ...] = ()
    errors: tuple[str, ...] = field(default_factory=tuple)


class DagValidator:
    """Validate node identity, edges, cycles, and the global node budget."""

    def __init__(self, max_nodes: int = 50) -> None:
        self._max_nodes = max_nodes

    def validate(self, nodes: dict[str, str], edges: list[tuple[str, str]]) -> DagValidationResult:
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
        graph = {node_id: set() for node_id in nodes}
        for source, target in edges:
            if source in nodes and target in nodes:
                graph[target].add(source)
        try:
            order = tuple(TopologicalSorter(graph).static_order())
        except CycleError:
            errors.append("cycle_detected")
            order = ()
        return DagValidationResult(ok=not errors, order=order, errors=tuple(dict.fromkeys(errors)))
