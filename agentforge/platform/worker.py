"""AgentForge 平台代码：worker。

本模块负责 worker 相关的平台能力，是 平台代码 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：run_worker。
"""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from agentforge.platform.infrastructure.db.base import create_session_factory
from agentforge.platform.observability.tracing import configure_tracing
from agentforge.platform.runtime import build_sqlalchemy_container, configure_container
from agentforge.platform.settings import get_settings
from agentforge.platform.workflows.support_ticket import (
    SupportTicketWorkflow,
    apply_approval_activity,
    intake_ticket_activity,
)

# 常量：TASK_QUEUE。
TASK_QUEUE = "support-copilot"


async def run_worker() -> None:
    """执行完整流程，并返回调用方需要的结果。

    Returns:
        None，函数执行后的结果。
    """
    settings = get_settings()
    configure_tracing(endpoint=settings.otel_exporter_otlp_endpoint)
    session_factory = create_session_factory(settings.database_url)
    configure_container(build_sqlalchemy_container(session_factory))

    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[SupportTicketWorkflow],
        activities=[intake_ticket_activity, apply_approval_activity],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
