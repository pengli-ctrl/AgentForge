"""通用 Temporal DAG 执行。"""

from datetime import timedelta

from temporalio import activity, workflow

from agentforge.orchestration.graph_validator import DagValidator

_RUNNER = None


def configure_node_runner(runner):
    """配置节点执行器。

    Args:
        runner: 异步节点执行函数。
    """
    global _RUNNER
    _RUNNER = runner


@activity.defn
async def execute_dag_node_activity(payload):
    """执行节点。

    Args:
        payload: 节点载荷。

    Raises:
        RuntimeError: 未配置执行器时抛出。

    Returns:
        节点结果。
    """
    if _RUNNER is None:
        raise RuntimeError("DAG runner not configured")
    return dict(await _RUNNER(payload["node_id"], payload["agent_name"], payload.get("input", {})))


@workflow.defn
class TemporalDagWorkflow:
    """执行扁平 DAG。"""

    @workflow.run
    async def run(self, payload):
        """执行 DAG。

        Args:
            payload: DAG 载荷。

        Raises:
            ValueError: DAG 非法时抛出。

        Returns:
            节点结果。
        """
        nodes = {str(n["node_id"]): str(n["agent_name"]) for n in payload.get("nodes", [])}
        edges = [(str(a), str(b)) for a, b in payload.get("edges", [])]
        check = DagValidator(int(payload.get("max_nodes", 50))).validate(nodes, edges)
        if not check.ok:
            raise ValueError("invalid DAG")
        out = {}
        for node_id in check.order:
            out[node_id] = await workflow.execute_activity(
                execute_dag_node_activity,
                {
                    "node_id": node_id,
                    "agent_name": nodes[node_id],
                    "input": payload.get("input", {}),
                },
                start_to_close_timeout=timedelta(
                    seconds=int(payload.get("node_timeout_seconds", 30))
                ),
            )
        return out
