"""提供架构升级适配。"""
from agentforge.orchestration.graph_validator import DagValidator


def test_dag_validator_returns_topological_order() -> None:
    """提供架构升级适配。
    """
    result = DagValidator().validate(
        {"a": "agent-a", "b": "agent-b", "c": "agent-c"},
        [("a", "b"), ("b", "c")],
    )
    assert result.ok is True
    assert result.order.index("a") < result.order.index("b") < result.order.index("c")


def test_dag_validator_rejects_cycle_and_unknown_edge() -> None:
    """提供架构升级适配。
    """
    result = DagValidator().validate({"a": "agent-a", "b": "agent-b"}, [("a", "b"), ("b", "a"), ("x", "a")])
    assert result.ok is False
    assert "cycle_detected" in result.errors
    assert "unknown_source:x" in result.errors


def test_dag_validator_rejects_node_budget() -> None:
    """提供架构升级适配。
    """
    result = DagValidator(max_nodes=1).validate({"a": "agent-a", "b": "agent-b"}, [])
    assert result.ok is False
    assert "max_nodes_exceeded" in result.errors
