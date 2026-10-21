"""控制台工单测试模块。

本测试模块验证 test_console_tickets 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_console_tickets_lists_and_filters、test_console_inbox_returns_only_waiting_approval、tes
    t_console_overview_includes_task_status_counts、test_console_costs_overview_aggregates_tenant
    s、test_ticket_list_pagination_cursor。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from agentforge.platform.modules.support.domain.ticket import (
    RiskLevel,
    Ticket,
    TicketPriority,
    TicketStatus,
)
from agentforge.platform.runtime import build_memory_container
from tests.platform.support_fixtures import configure_memory_support, create_app_with_support


def _ticket(
    ticket_id: str,
    status: TicketStatus,
    tenant_id: str = "tenant-a",
    risk: RiskLevel = RiskLevel.LOW,
    subject: str = "subject",
    assigned_team: str | None = None,
    assignee_id: str | None = None,
    queue: str | None = None,
    sla_due_at: datetime | None = None,
) -> Ticket:
    """处理工单。

    Args:
        ticket_id: 工单 ID。
        status: 目标状态。
        tenant_id: 租户 ID，用于数据隔离。
        risk: 风险。
        subject: 输入参数。
        assigned_team: 输入参数。
        assignee_id: 处理人 ID。
        queue: 队列。
        sla_due_at: SLA到期时间。

    Returns:
        工单结果。
    """
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
        assigned_team=assigned_team,
        assignee_id=assignee_id,
        metadata={
            "queue": queue,
            "sla": (
                {"due_at": sla_due_at.isoformat(), "status": "open"}
                if sla_due_at is not None
                else None
            ),
        },
    )


def _client():
    """处理客户端。

    Returns:
        处理结果。
    """
    container = build_memory_container()
    support = configure_memory_support(container)
    app = create_app_with_support(container, support)
    return container, support, TestClient(app)


async def _seed(support, tickets) -> None:
    """初始化初始数据。

    Args:
        support: 客服。
        tickets: 工单。
    """
    for t in tickets:
        await support.repository.save(t)


def test_console_tickets_lists_and_filters() -> None:
    """验证控制台工单及筛选条件对应的测试场景。"""
    from agentforge.platform.modules.support.infrastructure.memory_repository import (
        MemoryTicketRepository,
    )

    container, support, client = _client()
    assert isinstance(support.repository, MemoryTicketRepository)
    asyncio.run(
        _seed(
            support,
            [
                _ticket(
                    "t1",
                    TicketStatus.WAITING_APPROVAL,
                    risk=RiskLevel.HIGH,
                    assigned_team="finance-invoice-gate",
                    assignee_id="finance-bot",
                    queue="finance-invoice-gate",
                    sla_due_at=datetime.now(timezone.utc) - timedelta(minutes=5),
                ),
                _ticket("t2", TicketStatus.PUBLISHED, assigned_team="support"),
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

    finance = client.get(
        "/v1/console/tickets",
        params={"tenant_id": "tenant-a", "assigned_team": "finance-invoice-gate"},
    ).json()
    assert [t["ticket_id"] for t in finance["tickets"]] == ["t1"]

    assigned = client.get(
        "/v1/console/tickets",
        params={"tenant_id": "tenant-a", "assignee_id": "finance-bot"},
    ).json()
    assert [t["ticket_id"] for t in assigned["tickets"]] == ["t1"]

    queued = client.get(
        "/v1/console/tickets",
        params={"tenant_id": "tenant-a", "queue": "finance-invoice-gate"},
    ).json()
    assert [t["ticket_id"] for t in queued["tickets"]] == ["t1"]

    overdue = client.get(
        "/v1/console/tickets",
        params={"tenant_id": "tenant-a", "overdue": "true"},
    ).json()
    assert [t["ticket_id"] for t in overdue["tickets"]] == ["t1"]

    due_before = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    due = client.get(
        "/v1/console/tickets",
        params={"tenant_id": "tenant-a", "due_before": due_before},
    ).json()
    assert [t["ticket_id"] for t in due["tickets"]] == ["t1"]


def test_console_inbox_returns_only_waiting_approval() -> None:
    """验证控制台收件箱返回等待审批对应的测试场景。"""
    container, support, client = _client()
    asyncio.run(
        _seed(
            support,
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
    """验证控制台总览包含任务状态对应的测试场景。"""
    container, support, client = _client()
    asyncio.run(
        _seed(
            support,
            [
                _ticket(
                    "t1",
                    TicketStatus.WAITING_APPROVAL,
                    risk=RiskLevel.HIGH,
                    assigned_team="finance-invoice-gate",
                ),
                _ticket("t2", TicketStatus.PUBLISHED, assigned_team="support"),
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
    # 验证失败场景，确保异常路径能够被正确处理。
    assert tasks["failed"] == 0


def test_console_costs_overview_aggregates_tenants() -> None:
    """验证控制台成本总览聚合租户对应的测试场景。"""
    from agentforge.platform.domain.cost import CostRecord
    from agentforge.platform.infrastructure.memory_cost_repository import MemoryCostRepository

    container, support, client = _client()
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
    """验证工单查询分页游标对应的测试场景。"""
    container, support, client = _client()
    asyncio.run(
        _seed(support, [_ticket(f"t{i}", TicketStatus.NEW, subject=str(i)) for i in range(5)])
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
