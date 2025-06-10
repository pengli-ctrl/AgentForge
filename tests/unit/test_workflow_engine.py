"""工作流引擎测试 — YAML 解析/条件路由。

测试内容：
- 条件表达式解析（==, <, >, default）
- 条件表达式求值
- 工作流 YAML 加载
- 动态路由决策
"""

from __future__ import annotations

import os

import pytest

from agentforge.workflow.conditions import ConditionParser
from agentforge.workflow.engine import WorkflowEngine
from agentforge.workflow.registry import AgentRegistry


class TestConditionParser:
    """条件表达式解析器测试。"""

    @pytest.fixture
    def parser(self) -> ConditionParser:
        return ConditionParser()

    def test_equal_string(self, parser: ConditionParser) -> None:
        """等于比较（字符串）。"""
        assert (
            parser.evaluate("result.severity == 'critical'", {"result": {"severity": "critical"}})
            is True
        )
        assert (
            parser.evaluate("result.severity == 'critical'", {"result": {"severity": "warning"}})
            is False
        )

    def test_equal_number(self, parser: ConditionParser) -> None:
        """等于比较（数字）。"""
        assert parser.evaluate("result.count == 5", {"result": {"count": 5}}) is True
        assert parser.evaluate("result.count == 5", {"result": {"count": 3}}) is False

    def test_less_than(self, parser: ConditionParser) -> None:
        """小于比较。"""
        assert parser.evaluate("result.pass_rate < 0.8", {"result": {"pass_rate": 0.6}}) is True
        assert parser.evaluate("result.pass_rate < 0.8", {"result": {"pass_rate": 0.9}}) is False

    def test_greater_than(self, parser: ConditionParser) -> None:
        """大于比较。"""
        assert parser.evaluate("result.score > 80", {"result": {"score": 90}}) is True
        assert parser.evaluate("result.score > 80", {"result": {"score": 70}}) is False

    def test_not_equal(self, parser: ConditionParser) -> None:
        """不等于比较。"""
        assert (
            parser.evaluate("result.status != 'failed'", {"result": {"status": "success"}}) is True
        )
        assert (
            parser.evaluate("result.status != 'failed'", {"result": {"status": "failed"}}) is False
        )

    def test_default_condition(self, parser: ConditionParser) -> None:
        """default 条件始终为 True。"""
        assert parser.evaluate("default", {}) is True
        assert parser.evaluate("default", {"result": {}}) is True

    def test_boolean_check(self, parser: ConditionParser) -> None:
        """布尔检查（只有路径没有操作符）。"""
        assert (
            parser.evaluate("result.has_vulnerabilities", {"result": {"has_vulnerabilities": True}})
            is True
        )
        assert (
            parser.evaluate(
                "result.has_vulnerabilities", {"result": {"has_vulnerabilities": False}}
            )
            is False
        )
        assert parser.evaluate("result.has_vulnerabilities", {"result": {}}) is False

    def test_greater_equal(self, parser: ConditionParser) -> None:
        """大于等于比较。"""
        assert parser.evaluate("result.count >= 5", {"result": {"count": 5}}) is True
        assert parser.evaluate("result.count >= 5", {"result": {"count": 4}}) is False

    def test_less_equal(self, parser: ConditionParser) -> None:
        """小于等于比较。"""
        assert parser.evaluate("result.count <= 5", {"result": {"count": 5}}) is True
        assert parser.evaluate("result.count <= 5", {"result": {"count": 6}}) is False

    def test_nested_path(self, parser: ConditionParser) -> None:
        """嵌套路径解析。"""
        context = {"result": {"details": {"level": "critical"}}}
        assert parser.evaluate("result.details.level == 'critical'", context) is True


class TestWorkflowEngine:
    """工作流引擎测试。"""

    @pytest.fixture
    def config_dir(self) -> str:
        """获取工作流配置目录。"""
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "configs",
            "workflows",
        )

    @pytest.fixture
    def registry(self) -> AgentRegistry:
        """Agent 注册表。"""
        return AgentRegistry()

    @pytest.fixture
    def engine(self, registry: AgentRegistry, config_dir: str) -> WorkflowEngine:
        """工作流引擎。"""
        return WorkflowEngine(registry=registry, config_dir=config_dir)

    def test_load_workflow(self, engine: WorkflowEngine) -> None:
        """加载工作流 YAML。"""
        workflow = engine.load("code-review-pipeline")

        assert workflow.name == "code-review-pipeline"
        assert len(workflow.steps) > 0
        assert "code-review" in workflow.step_map
        assert "test-execution" in workflow.step_map
        assert "doc-generator" in workflow.step_map

    def test_load_security_workflow(self, engine: WorkflowEngine) -> None:
        """加载安全审查工作流。"""
        workflow = engine.load("security-review-pipeline")

        assert workflow.name == "security-review-pipeline"
        assert "security-scan" in workflow.step_map

    def test_get_next_agent_default(self, engine: WorkflowEngine) -> None:
        """默认路由 — 条件不匹配时走 default。"""
        workflow = engine.load("code-review-pipeline")

        next_agent = engine.get_next_agent(
            workflow,
            "code-review",
            {"severity": "info"},  # 不是 critical
        )

        assert next_agent == "test-execution"

    def test_get_next_agent_critical(self, engine: WorkflowEngine) -> None:
        """critical 路由 — 发现安全问题先跑安全扫描。"""
        workflow = engine.load("code-review-pipeline")

        next_agent = engine.get_next_agent(
            workflow,
            "code-review",
            {"severity": "critical"},
        )

        assert next_agent == "security-scan"

    def test_get_next_agent_test_fail(self, engine: WorkflowEngine) -> None:
        """测试不通过路由回代码审查。"""
        workflow = engine.load("code-review-pipeline")

        next_agent = engine.get_next_agent(
            workflow,
            "test-execution",
            {"pass_rate": 0.6},  # < 0.8
        )

        assert next_agent == "code-review"

    def test_get_next_agent_test_pass(self, engine: WorkflowEngine) -> None:
        """测试通过路由到文档生成。"""
        workflow = engine.load("code-review-pipeline")

        next_agent = engine.get_next_agent(
            workflow,
            "test-execution",
            {"pass_rate": 0.95},  # >= 0.8
        )

        assert next_agent == "doc-generator"

    def test_get_next_agent_complete(self, engine: WorkflowEngine) -> None:
        """文档生成完成路由到 complete。"""
        workflow = engine.load("code-review-pipeline")

        next_agent = engine.get_next_agent(
            workflow,
            "doc-generator",
            {},
        )

        assert next_agent == "complete"

    def test_get_next_agent_security_vulnerabilities(self, engine: WorkflowEngine) -> None:
        """安全扫描发现漏洞路由回代码审查。"""
        workflow = engine.load("code-review-pipeline")

        next_agent = engine.get_next_agent(
            workflow,
            "security-scan",
            {"has_vulnerabilities": True},
        )

        assert next_agent == "code-review"

    def test_list_workflows(self, engine: WorkflowEngine) -> None:
        """列出已加载的工作流。"""
        engine.load("code-review-pipeline")
        engine.load("security-review-pipeline")

        workflows = engine.list_workflows()
        assert "code-review-pipeline" in workflows
        assert "security-review-pipeline" in workflows
