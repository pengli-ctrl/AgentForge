"""Orchestrator 单元测试 — V2 串行编排器。

测试要点：Agent串联执行、状态传递、错误处理、编排流程。
"""

from __future__ import annotations

from typing import Any

import pytest

from agentforge.core.orchestrator import Orchestrator


class MockAgent:
    """用于测试的模拟智能体。"""

    def __init__(self, name: str, return_value: str = "result") -> None:
        """初始化模拟智能体。

        Args:
            name: 资源或对象名称。
            return_value: 返回值。
        """
        self.name = name
        self.return_value = return_value
        self.received_context: dict[str, Any] | None = None
        self.call_count: int = 0

    async def execute(self, context: dict[str, Any]) -> str:
        """执行模拟智能体。

        Args:
            context: 执行上下文。

        Returns:
            字符串结果。
        """
        self.received_context = dict(context)
        self.call_count += 1
        return f"{self.name}:{self.return_value}"


class MockStateStore:
    """Mock 状态存储。"""

    def __init__(self) -> None:
        """初始化模拟状态。"""
        self.store: dict[str, dict[str, Any]] = {}
        self.save_count: int = 0

    async def load_or_create(self, task_id: str) -> dict[str, Any]:
        """加载或创建。

        Args:
            task_id: 任务 ID。

        Returns:
            结构化结果字典。
        """
        return self.store.get(task_id, {})

    async def save(self, task_id: str, context: dict[str, Any]) -> None:
        """保存模拟状态。

        Args:
            task_id: 任务 ID。
            context: 执行上下文。
        """
        self.store[task_id] = context
        self.save_count += 1


class TestOrchestratorInit:
    """初始化测试。"""

    def test_init_warns_deprecation(self) -> None:
        """验证初始化弃用对应的测试场景。"""
        with pytest.warns(DeprecationWarning):
            orch = Orchestrator()
        assert orch.agents == {}
        assert orch.pipeline == []

    def test_init_with_state_store(self) -> None:
        """验证初始化使用状态存储对应的测试场景。"""
        store = MockStateStore()
        with pytest.warns(DeprecationWarning):
            orch = Orchestrator(state_store=store)
        assert orch.state_store is store


class TestAgentRegistration:
    """Agent 注册测试。"""

    def test_register_agent(self) -> None:
        """验证注册智能体对应的测试场景。"""
        with pytest.warns(DeprecationWarning):
            orch = Orchestrator()
        agent = MockAgent("review")
        orch.register_agent("review", agent)
        assert "review" in orch.agents
        assert orch.agents["review"] is agent

    def test_set_pipeline(self) -> None:
        """验证设置流水线对应的测试场景。"""
        with pytest.warns(DeprecationWarning):
            orch = Orchestrator()
        orch.set_pipeline(["step1", "step2", "step3"])
        assert orch.pipeline == ["step1", "step2", "step3"]


class TestSerialExecution:
    """串行执行测试。"""

    @pytest.mark.asyncio
    async def test_single_agent_execution(self) -> None:
        """验证单个智能体执行对应的测试场景。"""
        with pytest.warns(DeprecationWarning):
            orch = Orchestrator()
        agent = MockAgent("review")
        orch.register_agent("review", agent)
        orch.set_pipeline(["review"])

        results = await orch.execute("test task")
        assert "review" in results
        assert "review:result" in results["review"]
        assert agent.call_count == 1

    @pytest.mark.asyncio
    async def test_multiple_agents_in_sequence(self) -> None:
        """验证多个智能体在序列对应的测试场景。"""
        with pytest.warns(DeprecationWarning):
            orch = Orchestrator()
        agent1 = MockAgent("step1", "output1")
        agent2 = MockAgent("step2", "output2")
        orch.register_agent("step1", agent1)
        orch.register_agent("step2", agent2)
        orch.set_pipeline(["step1", "step2"])

        await orch.execute("test task")
        assert agent1.call_count == 1
        assert agent2.call_count == 1
        # 获取结果。
        assert "step1_result" in agent2.received_context

    @pytest.mark.asyncio
    async def test_context_accumulates(self) -> None:
        """验证上下文对应的测试场景。"""
        with pytest.warns(DeprecationWarning):
            orch = Orchestrator()
        agent1 = MockAgent("a", "r1")
        agent2 = MockAgent("b", "r2")
        agent3 = MockAgent("c", "r3")
        orch.register_agent("a", agent1)
        orch.register_agent("b", agent2)
        orch.register_agent("c", agent3)
        orch.set_pipeline(["a", "b", "c"])

        await orch.execute("task")
        # 获取结果。
        assert "a_result" in agent3.received_context
        assert "b_result" in agent3.received_context


class TestStateStoreIntegration:
    """状态存储集成测试。"""

    @pytest.mark.asyncio
    async def test_state_store_save_called(self) -> None:
        """验证状态存储保存调用的对应的测试场景。"""
        store = MockStateStore()
        with pytest.warns(DeprecationWarning):
            orch = Orchestrator(state_store=store)
        agent = MockAgent("review")
        orch.register_agent("review", agent)
        orch.set_pipeline(["review"])

        await orch.execute("task-id")
        assert store.save_count == 1

    @pytest.mark.asyncio
    async def test_state_store_load_called(self) -> None:
        """验证状态存储加载调用的对应的测试场景。"""
        store = MockStateStore()
        store.store["task-id"] = {"preloaded": True}
        with pytest.warns(DeprecationWarning):
            orch = Orchestrator(state_store=store)
        agent = MockAgent("review")
        orch.register_agent("review", agent)
        orch.set_pipeline(["review"])

        await orch.execute("task-id")

        assert agent.received_context.get("preloaded") is True
