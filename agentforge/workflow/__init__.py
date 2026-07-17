"""AgentForge Workflow 引擎模块 — YAML 工作流解析 + 条件路由执行。

核心组件：
- WorkflowEngine：解析 YAML 工作流配置，根据条件动态路由
- AgentRegistry：Agent 注册表，管理 Agent 名称→实例映射
- ConditionParser：条件表达式解析器
- LLMRouter：用 LLM 替代 if-else 路由决策
"""

from agentforge.workflow.conditions import ConditionParser
from agentforge.workflow.engine import Workflow, WorkflowEngine, WorkflowStep
from agentforge.workflow.llm_router import LLMRouter, RouteDecision
from agentforge.workflow.registry import AgentRegistry

__all__ = [
    "WorkflowEngine",
    "Workflow",
    "WorkflowStep",
    "AgentRegistry",
    "ConditionParser",
    "LLMRouter",
    "RouteDecision",
]
