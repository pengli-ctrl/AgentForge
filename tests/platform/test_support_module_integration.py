"""客服模块集成测试模块。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.bootstrap import build_support_module
from agentforge.platform.modules.support.infrastructure.memory_repository import (
    MemoryTicketRepository,
)
from agentforge.platform.modules.support.workflows.sla_sweep import SupportSlaSweepWorkflow
from agentforge.platform.modules.support.workflows.support_ticket import SupportTicketWorkflow
from agentforge.platform.runtime import build_memory_container, build_module_context


def test_platform_app_registers_support_module() -> None:
    """验证平台应用注册客服模块对应的测试场景。"""
    app = create_platform_app()
    registry = app.state.module_registry

    assert [module.manifest.name for module in registry.list_modules()] == ["support", "expense"]

    client = TestClient(app)
    response = client.post("/v1/support/events/im", json={})
    assert response.status_code == 422
    legacy_response = client.post("/v1/events/im", json={})
    assert legacy_response.status_code == 422


def test_support_module_exposes_workflow_and_activities() -> None:
    """验证客服模块工作流及活动对应的测试场景。"""
    container = build_memory_container()
    runtime = build_support_module(container, ticket_repository=MemoryTicketRepository()).build(
        build_module_context(container)
    )

    assert runtime.router is not None
    assert [router.prefix for router in runtime.legacy_routers] == ["/v1"]
    assert runtime.temporal_workflows == [SupportTicketWorkflow, SupportSlaSweepWorkflow]
    assert len(runtime.temporal_activities) == 3
    assert "support.ticket.sla_due_soon.v1" in runtime.event_handlers
    assert "support.ticket.sla_breached.v1" in runtime.event_handlers
