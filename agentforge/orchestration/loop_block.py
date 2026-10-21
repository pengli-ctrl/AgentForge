"""循环块模块。"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_SUB_DAG_MAX_NODES = 20
DEFAULT_SUB_DAG_TIMEOUT = 60.0  # 超时状态。
DEFAULT_SUB_DAG_MAX_PARALLEL = 3


@dataclass
class LoopResult:
    """循环结果相关组件。

    Attributes:
        success: 是否成功。
        iterations_completed: 迭代次数已完成。
        max_iterations: 最大迭代次数。
        final_output: 最终输出。
        exit_reason: 原因。
        iteration_results: 结果。
        total_cost: 总计成本。
        total_latency_ms: 总计。
        converged: 字段值。
    """

    success: bool
    iterations_completed: int
    max_iterations: int
    final_output: dict = field(default_factory=dict)
    exit_reason: str = ""
    iteration_results: list[dict] = field(default_factory=list)
    total_cost: float = 0.0
    total_latency_ms: float = 0.0
    converged: bool = False


class LoopBlock:
    """循环块相关组件。"""

    ABSOLUTE_MAX_ITERATIONS = 5

    def __init__(
        self,
        sub_dag,
        max_iterations: int = 5,
        exit_condition: Optional[Callable] = None,
        name: str = "loop_block",
        sub_dag_timeout: float = DEFAULT_SUB_DAG_TIMEOUT,
        sub_dag_max_nodes: int = DEFAULT_SUB_DAG_MAX_NODES,
        sub_dag_max_parallel: int = DEFAULT_SUB_DAG_MAX_PARALLEL,
    ):
        """初始化 LoopBlock。

        Args:
            sub_dag: DAG。
            max_iterations: 最大迭代次数。
            exit_condition: 输入参数。
            name: 资源或对象名称。
            sub_dag_timeout: DAG超时。
            sub_dag_max_nodes: DAG最大。
            sub_dag_max_parallel: DAG最大。
        """
        if max_iterations > self.ABSOLUTE_MAX_ITERATIONS:
            logger.warning(
                "LoopBlock[%s] max_iterations=%d exceeds hard limit of %d — capping",
                name,
                max_iterations,
                self.ABSOLUTE_MAX_ITERATIONS,
            )
        self._max_iterations = min(max_iterations, self.ABSOLUTE_MAX_ITERATIONS)
        self._sub_dag = sub_dag
        self._exit_condition = exit_condition or (lambda result, i: True)
        self._name = name
        self._sub_dag_timeout = sub_dag_timeout
        self._sub_dag_max_nodes = sub_dag_max_nodes
        self._sub_dag_max_parallel = sub_dag_max_parallel

    async def execute(
        self,
        context,
        agent_registry=None,
        tracer=None,
    ) -> LoopResult:
        """执行循环子图直到满足退出条件或达到最大轮次。

        Args:
            context: 执行上下文。
            agent_registry: 智能体注册表。
            tracer: 追踪器。

        Returns:
            循环结果结果。
        """
        start_time = time.monotonic()
        iteration_results = []
        total_cost = 0.0
        final_output: dict = {}
        converged = False
        exit_reason = ""

        for iteration in range(1, self._max_iterations + 1):

            await context.write("__loop_iteration__", iteration)
            await context.write("__loop_name__", self._name)
            await context.write("__loop_max__", self._max_iterations)

            try:
                from agentforge.orchestration.dag_engine import DAGEngine

                # 超时状态。
                sub_engine = DAGEngine(
                    max_nodes=self._sub_dag_max_nodes,
                    global_timeout=self._sub_dag_timeout,
                    max_parallel=self._sub_dag_max_parallel,
                )
                sub_result = await sub_engine.execute(
                    correlation_id=f"{self._name}_iter_{iteration}",
                    input_data=await context.get_all(),
                    dag=self._sub_dag,
                    agent_registry=agent_registry,
                    context=context,
                )

                iter_cost = sub_result.total_cost
                iter_latency = sub_result.total_latency
                total_cost += iter_cost
                final_output = sub_result.node_results

                iteration_results.append(
                    {
                        "iteration": iteration,
                        "success": sub_result.success_rate > 0,
                        "cost": iter_cost,
                        "latency_ms": iter_latency,
                        "output_keys": list(sub_result.node_results.keys()),
                    }
                )

            except asyncio.TimeoutError:
                iteration_results.append(
                    {
                        "iteration": iteration,
                        "success": False,
                        "error": "Sub-DAG timeout",
                    }
                )
                exit_reason = "timeout"
                break

            except Exception as e:
                logger.warning(
                    "LoopBlock[%s] iteration %d failed: %s",
                    self._name,
                    iteration,
                    str(e)[:200],
                )
                iteration_results.append(
                    {
                        "iteration": iteration,
                        "success": False,
                        "error": str(e)[:200],
                    }
                )
                if iteration == self._max_iterations:
                    exit_reason = "error"
                continue

            try:
                should_exit = self._exit_condition(final_output, iteration)
            except Exception as e:
                logger.warning(
                    "LoopBlock[%s] exit_condition raised: %s — stopping loop",
                    self._name,
                    str(e)[:200],
                )
                should_exit = True

            if should_exit:
                converged = True
                exit_reason = "condition_met"
                logger.info(
                    "LoopBlock[%s] converged at iteration %d",
                    self._name,
                    iteration,
                )
                break
        else:
            if not exit_reason:
                exit_reason = "max_iterations"
                logger.warning(
                    "LoopBlock[%s] reached max iterations (%d) without convergence — "
                    "marked as 'cannot auto-fix'",
                    self._name,
                    self._max_iterations,
                )

        elapsed_ms = (time.monotonic() - start_time) * 1000

        return LoopResult(
            success=converged,
            iterations_completed=len(iteration_results),
            max_iterations=self._max_iterations,
            final_output=final_output,
            exit_reason=exit_reason,
            iteration_results=iteration_results,
            total_cost=total_cost,
            total_latency_ms=elapsed_ms,
            converged=converged,
        )

    @property
    def name(self) -> str:
        """返回对象名称。

        Returns:
            字符串结果。
        """
        return self._name

    @property
    def max_iterations(self) -> int:
        """返回最大迭代次数。

        Returns:
            整数结果。
        """
        return self._max_iterations
