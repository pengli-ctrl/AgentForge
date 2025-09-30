from __future__ import annotations

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.domain.ticket import (
    RiskLevel,
    Ticket,
    TicketPriority,
    TicketStatus,
)
from agentforge.platform.runtime import build_memory_container


def _ticket(
    ticket_id: str,
    status: TicketStatus,
    tenant_id: str = "tenant-a",
    risk: RiskLevel = RiskLevel.LOW,
    subject: str = "subject",
) -> Ticket:
    return Ticket(
        ticket_id=ticket_id,
        tenant_id=tenant_id,
        customer_id="c1",
        source="email",
        subject=subject,
        status=status,
        priority=TicketPriority.P2,
        confidence=0.8,
        idempotency_key=f"ik-{ticket_id}",
        risk_level=risk,
    )


def _client():
    container = build_memory_container()
    app = create_platform_app(container)
    return container, TestClient(app)


async def _seed(container, tickets) -> None:
    for t in tickets:
        await container.repository.save(t)


def test_console_tickets_lists_and_filters() -> None:
    import asyncio

    from agentforge.platform.infrastructure.memory_ticket_repository import (
        MemoryTicketRepository,
    )

    container, client = _client()
    assert isinstance(container.repository, MemoryTicketRepository)
    asyncio.run(
        _seed(
            container,
            [
                _ticket("t1", TicketStatus.WAITING_APPROVAL, risk=RiskLevel.HIGH),
                _ticket("t2", TicketStatus.PUBLISHED),
            ],
        )
    )
    all_ = client.get("/v1/console/tickets", params={"tenant_id": "tenant-a"}).json()
    assert [t["ticket_id"] for t in all_["tickets"]] == ["t1", "t2"]
    assert all_["next_cursor"] is None

    only_approved = client.get(
        "/v1/console/tickets",
        params={"tenant_id": "tenant-a", "status": "waiting_approval"},
    ).json()
    assert [t["ticket_id"] for t in only_approved["tickets"]] == ["t1"]


def test_console_inbox_returns_only_waiting_approval() -> None:
    import asyncio

    container, client = _client()
    asyncio.run(
        _seed(
            container,
            [
                _ticket("t1", TicketStatus.WAITING_APPROVAL, risk=RiskLevel.HIGH),
                _ticket("t2", TicketStatus.READY_TO_PUBLISH),
                _ticket("t3", TicketStatus.PUBLISHED),
            ],
        )
    )
    inbox = client.get("/v1/console/inbox", params={"tenant_id": "tenant-a"}).json()
    assert [i["ticket_id"] for i in inbox["items"]] == ["t1"]
    assert inbox["items"][0]["risk_level"] == "high"


def test_console_overview_includes_task_status_counts() -> None:
    import asyncio

    container, client = _client()
    asyncio.run(
        _seed(
            container,
            [
                _ticket("t1", TicketStatus.WAITING_APPROVAL, risk=RiskLevel.HIGH),
                _ticket("t2", TicketStatus.PUBLISHED),
                _ticket(
                    "t3",
                    TicketStatus.FAILED,
                    tenant_id="other-tenant",
                ),
            ],
        )
    )
    overview = client.get("/v1/console/overview", params={"tenant_id": "tenant-a"}).json()
    tasks = overview["tasks"]
    assert tasks["waiting_approval"] == 1
    assert tasks["published"] == 1
    # other-tenant's failed ticket must NOT leak into tenant-a
    assert tasks["failed"] == 0


def test_console_costs_overview_aggregates_tenants() -> None:
    import asyncio

    from agentforge.platform.domain.cost import CostRecord
    from agentforge.platform.infrastructure.memory_cost_repository import (
        MemoryCostRepository,
    )

    container, client = _client()
    assert isinstance(container.cost_repository, MemoryCostRepository)
    for amount, tenant in [(10.0, "t1"), (5.0, "t2")]:
        container.cost_repository.records.append(
            CostRecord(
                tenant_id=tenant,
                task_id=f"task-{tenant}",
                model_name="gpt-x",
                provider="openai",
                input_tokens=100,
                output_tokens=50,
                amount=amount,
            )
        )
    client.put(
        "/v1/quotas/t1",
        json={"monthly_limit": 100.0, "warning_threshold": 0.8, "hard_limit": 1.0, "enabled": True},
    )
    costs = client.get("/v1/console/costs").json()
    assert costs["total_cost"] == 15.0
    tenants = {t["tenant_id"]: t for t in costs["tenants"]}
    assert tenants["t1"]["used"] == 10.0
    assert tenants["t2"]["used"] == 5.0
    assert tenants["t1"]["quota"]["configured"] is True
    assert tenants["t2"]["quota"]["configured"] is False


def test_ticket_list_pagination_cursor() -> None:
    import asyncio

    container, client = _client()
    asyncio.run(
        _seed(container, [_ticket(f"t{i}", TicketStatus.NEW, subject=str(i)) for i in range(5)])
    )
    page1 = client.get(
        "/v1/console/tickets",
        params={"tenant_id": "tenant-a", "limit": 2},
    ).json()
    assert len(page1["tickets"]) == 2
    assert page1["next_cursor"] is not None

    page2 = client.get(
        "/v1/console/tickets",
        params={"tenant_id": "tenant-a", "limit": 2, "cursor": page1["next_cursor"]},
    ).json()
    assert len(page2["tickets"]) == 2

    page3 = client.get(
        "/v1/console/tickets",
        params={"tenant_id": "tenant-a", "limit": 2, "cursor": page2["next_cursor"]},
    ).json()
    assert len(page3["tickets"]) == 1
    assert page3["next_cursor"] is None