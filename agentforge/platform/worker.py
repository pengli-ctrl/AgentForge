"""工作进程模块。"""

from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from agentforge.platform.core import ModuleRegistry
from agentforge.platform.infrastructure.db.base import create_session_factory
from agentforge.platform.module_catalog import (
    ModuleAssemblyContext,
    build_builtin_modules,
    build_module_config,
    build_support_notification_gateway,
)
from agentforge.platform.observability.tracing import configure_tracing
from agentforge.platform.runtime import (
    build_module_context,
    build_sqlalchemy_container,
    configure_container,
)
from agentforge.platform.settings import get_settings


async def run_worker() -> None:
    """运行工作进程。

    Raises:
        RuntimeError: 运行时依赖或状态不满足要求时抛出。
    """
    settings = get_settings()
    configure_tracing(endpoint=settings.otel_exporter_otlp_endpoint)
    session_factory = create_session_factory(settings.database_url)
    container = build_sqlalchemy_container(session_factory)
    configure_container(container)

    registry = ModuleRegistry(
        lambda manifest: build_module_context(
            container,
            config=build_module_config(manifest, settings),
        )
    )
    for module in build_builtin_modules(
        ModuleAssemblyContext(
            container=container,
            session_factory=session_factory,
            support_notification_gateway=build_support_notification_gateway(settings),
        )
    ):
        registry.register(module)
    registry.validate()
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    workers: list[Worker] = []
    for registered in registry.list_modules():
        runtime = registered.runtime
        if not runtime.temporal_workflows and not runtime.temporal_activities:
            continue
        workers.append(
            Worker(
                client,
                task_queue=registered.manifest.task_queue,
                workflows=runtime.temporal_workflows,
                activities=runtime.temporal_activities,
            )
        )
    if not workers:
        raise RuntimeError("no module Temporal workers were registered")
    await asyncio.gather(*(worker.run() for worker in workers))


if __name__ == "__main__":
    asyncio.run(run_worker())
