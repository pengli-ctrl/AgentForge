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

TASK_QUEUE = "support-copilot"


async def run_worker() -> None:
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
