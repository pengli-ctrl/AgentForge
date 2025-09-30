import asyncio

import pytest
from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.domain.rbac import Permission, Role, RoleAssignment
from agentforge.platform.domain.ticket import RiskLevel, Ticket, TicketPriority, TicketStatus
from agentforge.platform.infrastructure.memory_rbac_repository import MemoryRbacRepository
from agentforge.platform.runtime import ServiceContainer, build_memory_container


async def _seed_admin(rbac: MemoryRbacRepository) -> None:
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
        RoleAssignment(
            assignment_id="asg-1", tenant_id="t1", user_id="alice", role_id="r-admin"
        )
    )


@pytest.fixture(scope="module")
def client():
    container = build_memory_container()
    asyncio.run(_seed_admin(container.rbac_repository))
    app = create_platform_app(container)
    return TestClient(app), container


def test_authorize_endpoint_denied_unapproved(client):
    tc, _container = client
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
    tc, _container = client
    res = tc.post(
        "/v1/authorize", json={"principal": "alice", "action": "ticket.writeback"}
    )
    assert res.status_code == 422


def test_authorize_endpoint_records_audit(client):
    tc, container = client
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
    tc, container = client
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
    asyncio.run(container.repository.save(ticket))
    res = tc.post(
        "/v1/tickets/tk-unapprove/writeback",
        json={"tenant_id": "t1", "actor": "alice"},
    )
    assert res.status_code == 403