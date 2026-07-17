"""
AgentForge 快速开始示例 — 演示事件驱动多 Agent 编排的基本用法。

运行方式：
    python examples/quickstart.py

前置条件：
    1. 安装依赖：pip install -r requirements.txt
    2. 启动 Redis：redis-server
    3. 启动 vLLM 推理服务（或使用 Mock LLM）

本示例演示：
    1. 初始化事件总线
    2. 创建 Agent 并注册到事件总线
    3. 发布任务事件
    4. Agent 自动处理事件并产出结果
"""

import asyncio
import logging

from agentforge.core.event_bus import EventBus
from agentforge.core.event_types import AgentEvent, EventType
from agentforge.core.context_snapshot import ContextSnapshotManager
from agentforge.agents.code_review_agent import CodeReviewAgent
from agentforge.agents.test_execution_agent import TestExecutionAgent
from agentforge.agents.doc_generator_agent import DocGeneratorAgent
from agentforge.llm.gateway import LLMGateway, LLMResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class MockLLMGateway(LLMGateway):
    """Mock LLM Gateway — 用于示例演示，返回预设响应。"""

    async def chat(self, messages, tools=None, max_tokens=None, temperature=None):
        return LLMResponse(
            content="Mock LLM response: code review completed successfully.",
            model="mock-model",
            usage={"prompt_tokens": 100, "completion_tokens": 50},
        )


async def main():
    """快速开始主流程。"""

    # 1. 初始化事件总线和上下文快照管理器
    bus = EventBus(backend="redis", redis_url="redis://localhost:6379")
    snapshot_manager = ContextSnapshotManager()
    await bus.start()

    # 2. 创建 Agent
    llm = MockLLMGateway(model="mock-model")
    code_review = CodeReviewAgent(llm_gateway=llm)
    test_agent = TestExecutionAgent(llm_gateway=llm)
    doc_agent = DocGeneratorAgent(llm_gateway=llm)

    # 3. 注册 Agent 到事件总线
    bus.subscribe(EventType.TASK_SUBMITTED, code_review.execute)
    bus.subscribe(EventType.AGENT_COMPLETED, test_agent.execute)

    # 4. 创建上下文快照
    context = {
        "code_content": "def add(a, b): return a + b",
        "review_config": {"types": ["security", "logic", "style"]},
    }
    snapshot = snapshot_manager.create_snapshot("task-001", context)

    # 5. 发布任务事件
    task_event = AgentEvent(
        event_type=EventType.TASK_SUBMITTED,
        source_agent="api-gateway",
        payload={"task": "Review PR #42: Add addition function"},
        correlation_id="task-001",
        context_snapshot=snapshot.to_dict(),
    )

    logger.info("Publishing task event: %s", task_event.payload["task"])
    await bus.publish(task_event)

    # 6. 等待处理完成
    await asyncio.sleep(1)

    # 7. 清理
    await bus.stop()
    snapshot_manager.cleanup("task-001")

    logger.info("Quickstart completed!")


if __name__ == "__main__":
    asyncio.run(main())
