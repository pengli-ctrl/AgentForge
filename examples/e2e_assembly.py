"""
端到端组装示例 — EventBus + Agent + WorkflowEngine + CircuitBreaker 协同工作。

本示例展示 AgentForge V3 架构的三个核心组件如何组装成一个完整的
代码审查流水线，并展示 CircuitBreaker 熔断器如何保护 Agent 调用。

运行方式：
    python examples/e2e_assembly.py

流程概览：
    1. 创建 EventBus（内存模式）— Agent 间通信的枢纽
    2. 创建 AgentRegistry — 注册 CodeReviewAgent 和 TestExecutionAgent
    3. 创建 WorkflowEngine — 加载 code-review-pipeline 工作流
    4. 通过 EventBus 发布 TASK_SUBMITTED 事件触发流水线
    5. CodeReviewAgent 订阅事件并执行（ReAct 循环）
    6. 展示 Context Snapshot 状态隔离效果
    7. 展示 CircuitBreaker 熔断器保护机制
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

# 将项目根目录加入 sys.path，确保可以直接运行
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agentforge.core.event_bus import EventBus
from agentforge.core.event_types import AgentEvent, EventType
from agentforge.core.context_snapshot import ContextSnapshotManager
from agentforge.core.circuit_breaker import CircuitBreaker, CircuitState
from agentforge.agents.code_review_agent import CodeReviewAgent
from agentforge.agents.test_execution_agent import TestExecutionAgent
from agentforge.agents.doc_generator_agent import DocGeneratorAgent
from agentforge.llm.gateway import LLMGateway, LLMResponse
from agentforge.workflow.engine import WorkflowEngine
from agentforge.workflow.registry import AgentRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("e2e_assembly")


# ──────────────────────────────────────────────────────────────────────────
# Mock LLM Gateway — 模拟 LLM 推理服务（生产环境替换为 VLLMGateway）
# ──────────────────────────────────────────────────────────────────────────

class MockLLMGateway(LLMGateway):
    """Mock LLM Gateway — 返回预设的审查结果。

    生产环境中替换为 VLLMGateway，连接真实的 vLLM 推理服务。
    此 Mock 用于演示和测试，不依赖外部服务。
    """

    def __init__(self) -> None:
        super().__init__(model="mock-llm-v1")
        self._call_count = 0

    async def chat(
        self,
        messages: list[dict[str, str]] | str,
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        self._call_count += 1
        # 模拟 LLM 返回结构化的审查结果
        return LLMResponse(
            content=json.dumps({
                "summary": "代码质量良好，未发现严重问题",
                "severity": "info",
                "items": [],
            }, ensure_ascii=False),
            model="mock-llm-v1",
            usage={
                "prompt_tokens": 150,
                "completion_tokens": 80,
                "total_tokens": 230,
            },
        )


# ──────────────────────────────────────────────────────────────────────────
# 示例 1：EventBus + Agent 协同 — 事件驱动的 Agent 间通信
# ──────────────────────────────────────────────────────────────────────────

async def demo_event_bus_agent_communication() -> None:
    """演示 EventBus 驱动的 Agent 间通信。

    流程：
    1. 创建 EventBus（内存后端）
    2. 创建 CodeReviewAgent，订阅 TASK_SUBMITTED 事件
    3. 发布任务事件，Agent 自动处理
    4. Agent 执行完成后发布 AGENT_COMPLETED 事件
    """
    logger.info("=" * 70)
    logger.info("示例 1: EventBus + Agent 事件驱动通信")
    logger.info("=" * 70)

    # 创建事件总线（内存模式，适用于开发和测试）
    bus = EventBus(backend="memory")
    await bus.start()

    # 创建 Mock LLM 和 Agent
    llm = MockLLMGateway()
    code_review = CodeReviewAgent(llm_gateway=llm)

    # 用于接收 Agent 完成事件
    completed_events: list[AgentEvent] = []

    async def on_agent_completed(event: AgentEvent) -> None:
        """AGENT_COMPLETED 事件回调 — 接收 Agent 执行结果。"""
        completed_events.append(event)
        logger.info(
            "  ✓ 收到 AGENT_COMPLETED 事件 "
            "(source=%s, correlation_id=%s)",
            event.source_agent,
            event.correlation_id,
        )

    # CodeReviewAgent 的事件处理函数
    async def on_task_submitted(event: AgentEvent) -> None:
        """TASK_SUBMITTED 事件回调 — 触发 CodeReviewAgent 执行。"""
        logger.info("  → CodeReviewAgent 收到任务，开始执行...")
        result = await code_review.execute(event)
        logger.info("  ← CodeReviewAgent 执行完成，发布结果事件")
        # 将结果事件发布回事件总线
        await bus.publish(result)

    # 订阅事件
    bus.subscribe(EventType.TASK_SUBMITTED, on_task_submitted)
    bus.subscribe(EventType.AGENT_COMPLETED, on_agent_completed)

    # 创建上下文快照（状态隔离的基础）
    snapshot_manager = ContextSnapshotManager()
    context = {
        "code_content": "def add(a, b): return a + b",
        "review_config": {"types": ["security", "logic", "style"]},
        "code_path": "/test/code.py",
        "test_config": {"framework": "pytest"},
    }
    snapshot = snapshot_manager.create_snapshot("demo-001", context)

    # 发布任务事件 — 触发流水线
    task_event = AgentEvent(
        event_type=EventType.TASK_SUBMITTED,
        source_agent="api-gateway",
        payload={"task": "Review PR #42: Add addition function"},
        correlation_id="demo-001",
        context_snapshot=snapshot.to_dict(),
    )

    logger.info("  → 发布 TASK_SUBMITTED 事件: %s", task_event.payload["task"])
    await bus.publish(task_event)

    # 等待异步处理完成
    await asyncio.sleep(0.3)

    # 验证结果
    assert len(completed_events) >= 1, "应至少收到一个 AGENT_COMPLETED 事件"
    result_event = completed_events[0]
    logger.info(
        "  ✓ 验证通过: source=%s, event_type=%s",
        result_event.source_agent,
        result_event.event_type.value,
    )

    await bus.stop()
    snapshot_manager.cleanup("demo-001")
    logger.info("")


# ──────────────────────────────────────────────────────────────────────────
# 示例 2：WorkflowEngine — 完整工作流编排
# ──────────────────────────────────────────────────────────────────────────

async def demo_workflow_engine() -> None:
    """演示 WorkflowEngine 编排多 Agent 工作流。

    流程：
    1. 创建 AgentRegistry，注册 3 个 Agent
    2. 创建 WorkflowEngine，加载 code-review-pipeline 工作流
    3. 执行工作流：code-review → test-execution → doc-generator
    4. 展示条件路由：根据审查结果决定下一步
    """
    logger.info("=" * 70)
    logger.info("示例 2: WorkflowEngine 工作流编排")
    logger.info("=" * 70)

    # 创建 Mock LLM
    llm = MockLLMGateway()

    # 创建 Agent 并注册到 AgentRegistry
    registry = AgentRegistry()
    registry.register("code-review", CodeReviewAgent(llm_gateway=llm))
    registry.register("test-execution", TestExecutionAgent(llm_gateway=llm))
    registry.register("doc-generator", DocGeneratorAgent(llm_gateway=llm))

    logger.info("  → 已注册 Agent: %s", registry.list_names())

    # 创建 WorkflowEngine 并加载工作流配置
    config_dir = os.path.join(PROJECT_ROOT, "configs", "workflows")
    engine = WorkflowEngine(registry=registry, config_dir=config_dir)
    workflow = engine.load("code-review-pipeline")

    logger.info("  → 已加载工作流: %s (%d steps)", workflow.name, len(workflow.steps))

    # 执行工作流
    logger.info("  → 开始执行工作流...")
    result = await engine.execute(
        workflow_name="code-review-pipeline",
        correlation_id="workflow-demo-001",
        input_data={
            "code_content": "def add(a, b): return a + b",
            "review_config": {"types": ["security", "logic"]},
            "code_path": "/test/code.py",
            "test_config": {"framework": "pytest"},
            "task": "Review test code",
        },
    )

    logger.info("  ✓ 工作流执行完成，参与的 Agent: %s", list(result.keys()))
    for agent_name, agent_result in result.items():
        logger.info("    - %s: %s", agent_name, json.dumps(agent_result, ensure_ascii=False)[:100])

    engine.registry.clear()
    logger.info("")


# ──────────────────────────────────────────────────────────────────────────
# 示例 3：Context Snapshot 状态隔离
# ──────────────────────────────────────────────────────────────────────────

async def demo_context_snapshot_isolation() -> None:
    """演示 Context Snapshot 状态隔离机制。

    每个 Agent 只从 context_snapshot 中提取自己需要的上下文，
    不接收全量数据。这是 V3 架构解决 V2 context 无限膨胀的核心设计。

    展示：
    - CodeReviewAgent 只看到 code_content 和 review_config
    - TestExecutionAgent 只看到 code_path 和 test_config
    - 两个 Agent 看到的上下文互不干扰
    """
    logger.info("=" * 70)
    logger.info("示例 3: Context Snapshot 状态隔离")
    logger.info("=" * 70)

    llm = MockLLMGateway()

    # 创建两个 Agent
    code_review = CodeReviewAgent(llm_gateway=llm)
    test_agent = TestExecutionAgent(llm_gateway=llm)

    # 完整上下文（包含所有 Agent 的数据）
    full_context = {
        "code_content": "def add(a, b): return a + b",
        "review_config": {"types": ["security", "logic", "style"]},
        "code_path": "/test/code.py",
        "test_config": {"framework": "pytest"},
        "deploy_config": {"target": "staging"},
    }

    logger.info("  → 完整上下文 keys: %s", list(full_context.keys()))

    # CodeReviewAgent 提取上下文 — 只看 code_content 和 review_config
    cr_context = code_review._extract_context(full_context)
    logger.info("  → CodeReviewAgent 看到的 keys: %s", list(cr_context.keys()))
    assert "code_content" in cr_context, "CodeReviewAgent 应看到 code_content"
    assert "review_config" in cr_context, "CodeReviewAgent 应看到 review_config"
    assert "code_path" not in cr_context, "CodeReviewAgent 不应看到 code_path"
    assert "test_config" not in cr_context, "CodeReviewAgent 不应看到 test_config"

    # TestExecutionAgent 提取上下文 — 只看 code_path 和 test_config
    te_context = test_agent._extract_context(full_context)
    logger.info("  → TestExecutionAgent 看到的 keys: %s", list(te_context.keys()))
    assert "code_path" in te_context, "TestExecutionAgent 应看到 code_path"
    assert "test_config" in te_context, "TestExecutionAgent 应看到 test_config"
    assert "code_content" not in te_context, "TestExecutionAgent 不应看到 code_content"
    assert "review_config" not in te_context, "TestExecutionAgent 不应看到 review_config"

    logger.info("  ✓ 状态隔离验证通过: 每个 Agent 只看到自己需要的上下文")
    logger.info("")


# ──────────────────────────────────────────────────────────────────────────
# 示例 4：CircuitBreaker 熔断保护
# ──────────────────────────────────────────────────────────────────────────

async def demo_circuit_breaker() -> None:
    """演示 CircuitBreaker 熔断器保护 Agent 调用。

    当 Agent 连续失败时，熔断器自动切断调用，防止故障扩散。
    展示三态状态机：CLOSED → OPEN → HALF_OPEN → CLOSED

    场景：
    1. 模拟 Agent 连续失败 3 次 → 熔断器 OPEN
    2. 熔断状态下请求被快速拒绝（不调用 Agent）
    3. 恢复时间后 → HALF_OPEN，允许一次试探
    4. 试探成功 → CLOSED，恢复正常
    """
    logger.info("=" * 70)
    logger.info("示例 4: CircuitBreaker 熔断保护")
    logger.info("=" * 70)

    # 创建熔断器（阈值=3，恢复时间=2s，便于演示）
    breaker = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=2.0,
        half_open_max_calls=1,
    )

    logger.info("  → 初始状态: %s", breaker.state.value)
    assert breaker.state == CircuitState.CLOSED

    # 模拟连续失败 → 触发熔断
    logger.info("  → 模拟 Agent 连续失败 3 次...")
    for i in range(3):
        assert breaker.can_execute(), f"第 {i+1} 次请求应被放行（CLOSED 状态）"
        breaker.record_failure()
        logger.info(
            "    第 %d 次失败: state=%s, failures=%d",
            i + 1,
            breaker.state.value,
            breaker.failure_count,
        )

    # 熔断器应已 OPEN
    assert breaker.state == CircuitState.OPEN, "连续 3 次失败后应触发熔断"
    logger.info("  ✓ 熔断器已 OPEN — 后续请求将被快速拒绝")

    # 熔断状态下请求被拒绝
    assert not breaker.can_execute(), "OPEN 状态下请求应被拒绝"
    logger.info("  ✓ 熔断状态下请求被拒绝（快速失败，不调用 Agent）")

    # 等待恢复时间 → HALF_OPEN
    logger.info("  → 等待恢复时间 (%.1fs)...", 2.0)
    await asyncio.sleep(2.1)

    state = breaker.state
    assert state == CircuitState.HALF_OPEN, f"恢复时间后应为 HALF_OPEN, 实际: {state}"
    logger.info("  ✓ 熔断器进入 HALF_OPEN — 允许一次试探请求")

    # 试探请求成功 → 恢复 CLOSED
    assert breaker.can_execute(), "HALF_OPEN 状态应允许一次试探"
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED, "试探成功后应恢复 CLOSED"
    logger.info("  ✓ 试探成功 — 熔断器恢复 CLOSED，正常服务恢复")

    logger.info("")


# ──────────────────────────────────────────────────────────────────────────
# 示例 5：CircuitBreaker 保护 Agent 调用（完整场景）
# ──────────────────────────────────────────────────────────────────────────

class FailingAgent:
    """模拟一个会失败的 Agent，用于演示熔断器保护。"""

    def __init__(self, name: str, fail_times: int) -> None:
        self.name = name
        self._fail_times = fail_times
        self._call_count = 0

    async def execute(self, event: AgentEvent) -> AgentEvent:
        self._call_count += 1
        if self._call_count <= self._fail_times:
            raise RuntimeError(f"Agent {self.name} simulated failure #{self._call_count}")
        # 成功
        return AgentEvent(
            event_type=EventType.AGENT_COMPLETED,
            source_agent=self.name,
            payload={"result": "success after recovery"},
            correlation_id=event.correlation_id,
        )


async def demo_circuit_breaker_protecting_agent() -> None:
    """演示 CircuitBreaker 保护 Agent 调用的完整场景。

    展示熔断器如何包裹 Agent.execute()，在故障时快速降级。
    """
    logger.info("=" * 70)
    logger.info("示例 5: CircuitBreaker 保护 Agent 调用（完整场景）")
    logger.info("=" * 70)

    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
    agent = FailingAgent(name="flaky-agent", fail_times=3)

    async def call_agent_with_breaker(event: AgentEvent) -> AgentEvent:
        """通过熔断器保护调用 Agent。

        熔断器 OPEN 时快速返回降级结果，不调用 Agent。
        """
        if not breaker.can_execute():
            logger.info("    [熔断器] 请求被拒绝 — 返回降级结果")
            return AgentEvent(
                event_type=EventType.AGENT_FAILED,
                source_agent="circuit-breaker",
                payload={"result": "降级处理: Agent 暂时不可用"},
                correlation_id=event.correlation_id,
            )

        try:
            result = await agent.execute(event)
            breaker.record_success()
            logger.info("    [熔断器] Agent 调用成功")
            return result
        except Exception as e:
            breaker.record_failure()
            logger.warning("    [熔断器] Agent 调用失败: %s (failures=%d)", e, breaker.failure_count)
            return AgentEvent(
                event_type=EventType.AGENT_FAILED,
                source_agent="circuit-breaker",
                payload={"result": f"Agent 失败: {e}"},
                correlation_id=event.correlation_id,
            )

    test_event = AgentEvent(
        event_type=EventType.TASK_SUBMITTED,
        source_agent="test",
        payload={"task": "test"},
        correlation_id="breaker-demo",
    )

    # 前 3 次调用：Agent 失败，熔断器记录失败
    logger.info("  → 阶段 1: Agent 连续失败，熔断器逐渐打开")
    for i in range(3):
        result = await call_agent_with_breaker(test_event)
        logger.info("    调用 %d 结果: %s, 熔断器状态: %s", i + 1, result.event_type.value, breaker.state.value)

    # 第 4 次调用：熔断器 OPEN，快速降级
    logger.info("  → 阶段 2: 熔断器 OPEN，快速降级")
    result = await call_agent_with_breaker(test_event)
    assert result.source_agent == "circuit-breaker", "应返回降级结果"
    logger.info("    调用 4 结果: %s (快速降级，未调用 Agent)", result.event_type.value)

    # 等待恢复
    logger.info("  → 阶段 3: 等待恢复时间后试探...")
    await asyncio.sleep(1.1)

    # 第 5 次调用：HALF_OPEN，Agent 已恢复正常
    result = await call_agent_with_breaker(test_event)
    logger.info("    调用 5 结果: %s, 熔断器状态: %s", result.event_type.value, breaker.state.value)
    assert breaker.state == CircuitState.CLOSED, "试探成功后应恢复 CLOSED"

    logger.info("  ✓ 熔断器保护演示完成 — Agent 故障被隔离，系统自动恢复")
    logger.info("")


# ──────────────────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────────────────

async def main() -> None:
    """运行所有端到端组装示例。"""
    logger.info("=" * 70)
    logger.info("AgentForge 端到端组装示例")
    logger.info("EventBus + Agent + WorkflowEngine + CircuitBreaker")
    logger.info("=" * 70)
    logger.info("")

    # 示例 1: EventBus + Agent 事件驱动通信
    await demo_event_bus_agent_communication()

    # 示例 2: WorkflowEngine 工作流编排
    await demo_workflow_engine()

    # 示例 3: Context Snapshot 状态隔离
    await demo_context_snapshot_isolation()

    # 示例 4: CircuitBreaker 熔断保护（基本状态机）
    await demo_circuit_breaker()

    # 示例 5: CircuitBreaker 保护 Agent 调用（完整场景）
    await demo_circuit_breaker_protecting_agent()

    logger.info("=" * 70)
    logger.info("所有示例执行完成！")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
