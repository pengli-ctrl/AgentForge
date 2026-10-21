"""API测试模块。

本测试模块验证 test_authorization_api 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：client、test_authorize_endpoint_denied_unapproved、test_authorize_endpoint_requires_tenant、te
    st_authorize_endpoint_records_audit、test_writeback_403_unapproved。
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from agentforge.platform.domain.rbac import Permission, Role, RoleAssignment
from agentforge.platform.infrastructure.memory_rbac_repository import MemoryRbacRepository
from agentforge.platform.modules.support.domain.ticket import (
    RiskLevel,
    Ticket,
    TicketPriority,
    TicketStatus,
)
from agentforge.platform.runtime import build_memory_container
from tests.platform.support_fixtures import configure_memory_support, create_app_with_support


async def _seed_admin(rbac: MemoryRbacRepository) -> None:
    """初始化管理。

    Args:
        rbac: RBAC。
    """
    await rbac.save_role(
        Role(
            role_id="r-admin",
            tenant_id="t1",
            name="support_admin",
            description="",
            permissions=[Permission.TICKET_WRITEBACK, Permission.TICKET_READ],
            built_in=True,
        )
    )
    await rbac.save_assignment(
        RoleAssignment(assignment_id="asg-1", tenant_id="t1", user_id="alice", role_id="r-admin")
    )


@pytest.fixture(scope="module")
def client():
    """处理客户端。

    Returns:
        处理结果。
    """
    container = build_memory_container()
    asyncio.run(_seed_admin(container.rbac_repository))
    support = configure_memory_support(container)
    app = create_app_with_support(container, support)
    return TestClient(app), container, support


def test_authorize_endpoint_denied_unapproved(client):
    """验证授权端点拒绝未批准对应的测试场景。

    Args:
        client: 客户端实例。
    """
    tc, _container, _support = client
    res = tc.post(
        "/v1/authorize",
        json={
            "tenant_id": "t1",
            "principal": "alice",
            "action": "ticket.writeback",
            "resource_type": "ticket",
            "resource_id": "ticket-a",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["outcome"] in {"denied", "requires_approval"}


def test_authorize_endpoint_requires_tenant(client):
    """验证授权端点要求租户对应的测试场景。

    Args:
        client: 客户端实例。
    """
    tc, _container, _support = client
    res = tc.post("/v1/authorize", json={"principal": "alice", "action": "ticket.writeback"})
    assert res.status_code == 422


def test_authorize_endpoint_records_audit(client):
    """验证授权端点记录审计对应的测试场景。

    Args:
        client: 客户端实例。
    """
    tc, container, support = client
    tc.post(
        "/v1/authorize",
        json={
            "tenant_id": "t1",
            "principal": "nobody",
            "action": "ticket.writeback",
            "resource_type": "ticket",
            "resource_id": "ticket-b",
        },
    )
    events = asyncio.run(container.audit_repository.list_events("t1"))
    assert any(e.action == "ticket.writeback.authorization" for e in events)


def test_writeback_403_unapproved(client):
    """验证写回未批准对应的测试场景。

    Args:
        client: 客户端实例。
    """
    tc, container, support = client
    ticket = Ticket(
        ticket_id="tk-unapprove",
        tenant_id="t1",
        customer_id="c1",
        conversation_id="cv1",
        source="feishu",
        subject="Hi",
        status=TicketStatus.WAITING_APPROVAL,
        priority=TicketPriority.P2,
        risk_level=RiskLevel.HIGH,
        idempotency_key="ik-wb-403",
    )
    asyncio.run(support.repository.save(ticket))
    res = tc.post(
        "/v1/tickets/tk-unapprove/writeback",
        json={"tenant_id": "t1", "actor": "alice"},
    )
    assert res.status_code == 403
