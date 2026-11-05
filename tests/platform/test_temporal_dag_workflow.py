"""测试通用 Temporal DAG 定义。"""

from agentforge.orchestration.temporal_dag import TemporalDagWorkflow, execute_dag_node_activity


def test_temporal_dag_workflow_is_declared():
    """验证工作流和节点活动已声明。"""
    assert TemporalDagWorkflow.__name__ == "TemporalDagWorkflow"
    assert callable(execute_dag_node_activity)
