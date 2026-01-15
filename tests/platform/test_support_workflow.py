"""AgentForge 平台测试层：test_support_workflow。

本测试模块验证 test_support_workflow 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：test_temporal_workflow_reaches_waiting_review。
"""

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from agentforge.platform.runtime import build_memory_container, configure_container
from agentforge.platform.workflows.support_ticket import (
    SupportTicketWorkflow,
    intake_ticket_activity,
)


@pytest.mark.asyncio
@pytest.mark.slow
async def test_temporal_workflow_reaches_waiting_review() -> None:
    """验证 temporal_workflow_reaches_waiting_review 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    container = build_memory_container()
    await container.knowledge_service.ingest_document(
        tenant_id="tenant-1",
        title="Product usage",
        content="How to use this product: open the dashboard and follow the setup guide.",
    )
    configure_container(container)
    env = await WorkflowEnvironment.start_time_skipping()
    try:
        worker = Worker(
            env.client,
            task_queue="support-copilot-test",
            workflows=[SupportTicketWorkflow],
            activities=[intake_ticket_activity],
        )
        async with worker:
            handle = await env.client.start_workflow(
                SupportTicketWorkflow.run,
                {
                    "tenant_id": "tenant-1",
                    "source": "feishu",
                    "message_id": "temporal-msg-1",
                    "text": "How do I use this product?",
                },
                id="temporal-task-1",
                task_queue="support-copilot-test",
            )
            result = await handle.result()
            assert result["status"] == "waiting_review"
            assert result["metadata"]["draft"]["citations"]
    finally:
        await env.shutdown()
