"""AgentForge 编排执行层：loop_block。

本模块负责 loop_block 相关能力，是 编排执行层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：LoopResult、LoopBlock。
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# 说明：该步骤用于实现上述逻辑并保证行为稳定。
# 说明：该步骤用于实现上述逻辑并保证行为稳定。
DEFAULT_SUB_DAG_MAX_NODES = 20  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
DEFAULT_SUB_DAG_TIMEOUT = 60.0  # 超时状态。
DEFAULT_SUB_DAG_MAX_PARALLEL = 3  # 说明：该步骤用于实现上述逻辑并保证行为稳定。


@dataclass
class LoopResult:
    """LoopResult。

    LoopResult 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - success: bool。
    - iterations_completed: int。
    - max_iterations: int。
    - final_output: dict。
    - exit_reason: str。
    - iteration_results: list[dict]。
    - total_cost: float。
    - total_latency_ms: float。
    - converged: bool。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    success: bool
    iterations_completed: int
    max_iterations: int
    final_output: dict = field(default_factory=dict)
    exit_reason: str = ""  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    iteration_results: list[dict] = field(default_factory=list)
    total_cost: float = 0.0
    total_latency_ms: float = 0.0
    converged: bool = False  # 说明：该步骤用于实现上述逻辑并保证行为稳定。


class LoopBlock:
    """LoopBlock。

    LoopBlock 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - ABSOLUTE_MAX_ITERATIONS: 5。
    - 方法 execute()。
    - 方法 name()。
    - 方法 max_iterations()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    ABSOLUTE_MAX_ITERATIONS = 5

    def __init__(
        self,
        sub_dag,  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        max_iterations: int = 5,
        exit_condition: Optional[Callable] = None,
        name: str = "loop_block",
        sub_dag_timeout: float = DEFAULT_SUB_DAG_TIMEOUT,
        sub_dag_max_nodes: int = DEFAULT_SUB_DAG_MAX_NODES,
        sub_dag_max_parallel: int = DEFAULT_SUB_DAG_MAX_PARALLEL,
    ):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            sub_dag: Any，调用方传入的 sub_dag 参数。
            max_iterations: int，调用方传入的 max_iterations 参数。
            exit_condition: Optional[Callable]，调用方传入的 exit_condition 参数。
            name: str，调用方传入的 name 参数。
            sub_dag_timeout: float，调用方传入的 sub_dag_timeout 参数。
            sub_dag_max_nodes: int，调用方传入的 sub_dag_max_nodes 参数。
            sub_dag_max_parallel: int，调用方传入的 sub_dag_max_parallel 参数。

        Returns:
            None，函数执行后的结果。
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
        context,  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        agent_registry=None,
        tracer=None,
    ) -> LoopResult:
        """执行 execute 对应的逻辑，并返回处理结果。

        Args:
            context: Any，调用方传入的 context 参数。
            agent_registry: Any，调用方传入的 agent_registry 参数。
            tracer: Any，调用方传入的 tracer 参数。

        Returns:
            LoopResult，函数执行后的结果。
        """
        start_time = time.monotonic()
        iteration_results = []
        total_cost = 0.0
        final_output: dict = {}
        converged = False
        exit_reason = ""

        for iteration in range(1, self._max_iterations + 1):

            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            # Agent 注册与查询。
            await context.write("__loop_iteration__", iteration)
            await context.write("__loop_name__", self._name)
            await context.write("__loop_max__", self._max_iterations)

            try:
                # 说明：该步骤用于实现上述逻辑并保证行为稳定。
                # 说明：该步骤用于实现上述逻辑并保证行为稳定。
                from agentforge.orchestration.dag_engine import DAGEngine

                # 说明：该步骤用于实现上述逻辑并保证行为稳定。
                # 说明：该步骤用于实现上述逻辑并保证行为稳定。
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
                # 说明：该步骤用于实现上述逻辑并保证行为稳定。
                if iteration == self._max_iterations:
                    exit_reason = "error"
                continue

            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            try:
                should_exit = self._exit_condition(final_output, iteration)
            except Exception as e:
                logger.warning(
                    "LoopBlock[%s] exit_condition raised: %s — stopping loop",
                    self._name,
                    str(e)[:200],
                )
                should_exit = True  # 说明：该步骤用于实现上述逻辑并保证行为稳定。

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
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
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
        """执行 name 对应的逻辑，并返回处理结果。

        Returns:
            str，函数执行后的结果。
        """
        return self._name

    @property
    def max_iterations(self) -> int:
        """执行 max_iterations 对应的逻辑，并返回处理结果。

        Returns:
            int，函数执行后的结果。
        """
        return self._max_iterations
