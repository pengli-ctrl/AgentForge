"""引擎模块。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import yaml

from agentforge.workflow.conditions import ConditionParser
from agentforge.workflow.registry import AgentRegistry

logger = logging.getLogger(__name__)


@dataclass
class WorkflowStep:
    """工作流中的单个执行步骤。

    Attributes:
        agent: 智能体。
        on_complete: 时完成。
    """

    agent: str
    on_complete: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Workflow:
    """工作流的 Temporal 工作流。

    Attributes:
        name: 名称。
        description: 描述信息。
        steps: 字段值。
        step_map: 步骤。
    """

    name: str = ""
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    step_map: dict[str, WorkflowStep] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验并补全初始化后的字段。"""
        for step in self.steps:
            self.step_map[step.agent] = step


class WorkflowEngine:
    """工作流引擎相关组件。"""

    def __init__(
        self,
        registry: AgentRegistry,
        config_dir: str = "configs/workflows",
    ) -> None:
        """初始化 WorkflowEngine。

        Args:
            registry: 注册表实例。
            config_dir: 配置。
        """
        self.registry = registry
        self.config_dir = config_dir
        self._workflows: dict[str, Workflow] = {}
        self._condition_parser = ConditionParser()
        self._max_iterations: int = 20  # 防止无限循环

    def load(self, workflow_name: str) -> Workflow:
        """加载工作流引擎。

        Args:
            workflow_name: 工作流名称。

        Returns:
            工作流结果。

        Raises:
            FileNotFoundError: 操作无法完成时抛出。
            ValueError: 输入值或业务状态不合法时抛出。
        """
        import os

        file_path = os.path.join(self.config_dir, f"{workflow_name}.yaml")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Workflow config not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "steps" not in data:
            raise ValueError(f"Invalid workflow config: missing 'steps' in {file_path}")

        steps: list[WorkflowStep] = []
        for step_data in data["steps"]:
            steps.append(
                WorkflowStep(
                    agent=step_data["agent"],
                    on_complete=step_data.get("on_complete", []),
                )
            )

        workflow = Workflow(
            name=data.get("name", workflow_name),
            description=data.get("description", ""),
            steps=steps,
        )

        self._workflows[workflow_name] = workflow
        logger.info(
            "Workflow loaded (name=%s, steps=%d)",
            workflow_name,
            len(steps),
        )

        return workflow

    def get_workflow(self, name: str) -> Workflow | None:
        """获取已加载的工作流。

        Args:
            name: 资源或对象名称。

        Returns:
            工作流无结果。
        """
        return self._workflows.get(name)

    def list_workflows(self) -> list[str]:
        """列出所有已加载的工作流名称。

        Returns:
            结果列表。
        """
        return list(self._workflows.keys())

    def get_next_agent(
        self,
        workflow: Workflow,
        current_agent: str,
        agent_result: dict[str, Any],
    ) -> str | None:
        """获取下一个智能体。

        Args:
            workflow: 工作流定义或实例。
            current_agent: 智能体。
            agent_result: 智能体结果。

        Returns:
            无结果。
        """
        step = workflow.step_map.get(current_agent)
        if step is None:
            logger.warning(
                "Agent not found in workflow (agent=%s, workflow=%s)",
                current_agent,
                workflow.name,
            )
            return None

        # 构建求值上下文
        context = {"result": agent_result}

        for route in step.on_complete:
            condition = route.get("condition", "default")
            next_agent = route.get("next", "")

            if self._condition_parser.evaluate(condition, context):
                logger.info(
                    "Route decision (workflow=%s, from=%s, to=%s, condition=%s)",
                    workflow.name,
                    current_agent,
                    next_agent,
                    condition,
                )
                return next_agent

        logger.warning(
            "No matching route (workflow=%s, agent=%s)",
            workflow.name,
            current_agent,
        )
        return None

    async def execute(
        self,
        workflow_name: str,
        correlation_id: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """执行核心处理逻辑并返回结果。

        Args:
            workflow_name: 工作流名称。
            correlation_id: 用于关联同一业务链路的关联 ID。
            input_data: 输入数据。

        Returns:
            结构化结果字典。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        workflow = self._workflows.get(workflow_name)
        if workflow is None:
            workflow = self.load(workflow_name)

        if not workflow.steps:
            raise ValueError(f"Workflow '{workflow_name}' has no steps")

        results: dict[str, Any] = {}
        context_snapshot: dict[str, Any] = dict(input_data)
        current_agent_name = workflow.steps[0].agent
        iteration = 0

        logger.info(
            "Workflow started (name=%s, correlation_id=%s, first_agent=%s)",
            workflow_name,
            correlation_id,
            current_agent_name,
        )

        while current_agent_name and current_agent_name != "complete":
            iteration += 1
            if iteration > self._max_iterations:
                logger.error(
                    "Workflow exceeded max iterations (name=%s, correlation_id=%s, "
                    "iterations=%d)",
                    workflow_name,
                    correlation_id,
                    iteration,
                )
                results["_error"] = "Max iterations exceeded"
                break

            agent = self.registry.get(current_agent_name)
            if agent is None:
                raise ValueError(f"Agent '{current_agent_name}' not registered")

            logger.info(
                "Workflow executing agent (name=%s, agent=%s, iteration=%d)",
                workflow_name,
                current_agent_name,
                iteration,
            )

            # 执行 Agent
            agent_result = await self._execute_agent(
                agent, current_agent_name, correlation_id, context_snapshot
            )

            results[current_agent_name] = agent_result
            context_snapshot[f"{current_agent_name}_result"] = agent_result

            # 决定下一个 Agent
            current_agent_name = self.get_next_agent(workflow, current_agent_name, agent_result)

        logger.info(
            "Workflow completed (name=%s, correlation_id=%s, iterations=%d, " "agents_executed=%s)",
            workflow_name,
            correlation_id,
            iteration,
            list(results.keys()),
        )

        return results

    async def _execute_agent(
        self,
        agent: Any,
        agent_name: str,
        correlation_id: str,
        context_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """执行智能体。

        Args:
            agent: 智能体。
            agent_name: 智能体名称。
            correlation_id: 用于关联同一业务链路的关联 ID。
            context_snapshot: 上下文快照。

        Returns:
            结构化结果字典。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        from agentforge.core.event_types import AgentEvent, EventType

        # 构造事件
        event = AgentEvent(
            event_type=EventType.TASK_SUBMITTED,
            source_agent="workflow-engine",
            target_agent=agent_name,
            payload={"task": context_snapshot.get("task", "")},
            correlation_id=correlation_id,
            context_snapshot=context_snapshot,
        )

        # 如果 Agent 有 execute 方法（V3 Agent 基类）
        if hasattr(agent, "execute"):
            result_event = await agent.execute(event)
            result_value = result_event.payload.get("result", "")
            # 尝试 JSON 解析（LLM 通常返回 JSON 格式结果）
            if isinstance(result_value, str):
                try:
                    import json

                    return json.loads(result_value)
                except (json.JSONDecodeError, TypeError):
                    return {"output": result_value}
            return result_value if isinstance(result_value, dict) else {"output": str(result_value)}

        # 如果 Agent 是可调用对象
        if callable(agent):
            return await agent(context_snapshot)

        raise ValueError(
            f"Agent '{agent_name}' is not executable " f"(no execute method, not callable)"
        )
