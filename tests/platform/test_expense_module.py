"""测试报销模块测试模块。"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.domain.rbac import Role, RoleAssignment
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.modules.expense.domain.claim import ExpenseClaimStatus
from agentforge.platform.modules.expense.infrastructure.memory_repository import (
    MemoryExpenseClaimRepository,
)
from agentforge.platform.modules.expense.infrastructure.sqlalchemy_repository import (
    SQLAlchemyExpenseClaimRepository,
)
from agentforge.platform.runtime import build_memory_container


def _payload(idempotency_key: str, tenant_id: str = "tenant-1") -> dict[str, object]:
    """处理载荷。

    Args:
        idempotency_key: 幂等键，用于避免重复处理。
        tenant_id: 租户 ID，用于数据隔离。

    Returns:
        结构化结果字典。
    """
    return {
        "tenant_id": tenant_id,
        "applicant_id": "employee-1",
        "amount_cents": 12800,
        "currency": "CNY",
        "expense_date": "2026-10-18",
        "category": "travel",
        "description": "Client visit",
        "invoice_count": 1,
        "idempotency_key": idempotency_key,
        "trace_id": "trace-expense-1",
    }


def test_expense_manual_entry_and_submit_flow() -> None:
    """验证报销条目及提交对应的测试场景。"""
    container = build_memory_container()
    repository = MemoryExpenseClaimRepository()
    app = create_platform_app(container, expense_claim_repository=repository)
    client = TestClient(app)

    created = client.post("/v1/expense/claims", json=_payload("expense-idem-1"))
    assert created.status_code == 200
    claim = created.json()
    assert claim["status"] == ExpenseClaimStatus.DRAFT.value
    assert claim["amount_cents"] == 12800

    duplicate = client.post("/v1/expense/claims", json=_payload("expense-idem-1"))
    assert duplicate.status_code == 200
    assert duplicate.json()["claim_id"] == claim["claim_id"]

    listed = client.get("/v1/expense/claims", params={"tenant_id": "tenant-1"})
    assert listed.status_code == 200
    assert [item["claim_id"] for item in listed.json()["claims"]] == [claim["claim_id"]]

    isolated = client.get("/v1/expense/claims", params={"tenant_id": "tenant-2"})
    assert isolated.status_code == 200
    assert isolated.json()["claims"] == []

    submitted = client.post(
        f"/v1/expense/claims/{claim['claim_id']}/submit",
        json={"tenant_id": "tenant-1"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == ExpenseClaimStatus.WAITING_APPROVAL.value

    pending = asyncio.run(container.outbox_store.fetch_pending())
    assert [event.event_type for event in pending] == [
        "expense.claim.created.v1",
        "expense.claim.submitted.v1",
    ]

    audit = client.get(
        "/v1/audit",
        params={"tenant_id": "tenant-1", "resource_id": claim["claim_id"]},
    ).json()["events"]
    assert {event["action"] for event in audit} == {
        "expense.claim.created",
        "expense.claim.submitted",
    }


def test_expense_routes_are_isolated_and_validate_payloads() -> None:
    """验证报销路由为隔离及对应的测试场景。"""
    client = TestClient(create_platform_app())

    missing_tenant = client.post("/v1/expense/claims", json={"amount_cents": 100})
    assert missing_tenant.status_code == 422

    created = client.post("/v1/expense/claims", json=_payload("expense-idem-2")).json()
    wrong_tenant = client.get(
        f"/v1/expense/claims/{created['claim_id']}",
        params={"tenant_id": "tenant-2"},
    )
    assert wrong_tenant.status_code == 404


@pytest.mark.asyncio
async def test_sqlalchemy_expense_repository_round_trip() -> None:
    """验证SQLAlchemy报销仓储轮次往返对应的测试场景。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = SQLAlchemyExpenseClaimRepository(session_factory)
    container = build_memory_container()
    app = create_platform_app(container, expense_claim_repository=repository)
    client = TestClient(app)

    created = client.post("/v1/expense/claims", json=_payload("expense-idem-sql"))
    assert created.status_code == 200
    claim_id = created.json()["claim_id"]
    stored = await repository.get("tenant-1", claim_id)
    assert stored is not None
    assert stored.amount_cents == 12800
    snapshot = await repository.list_all(
        "tenant-1",
        status=ExpenseClaimStatus.DRAFT,
    )
    assert [item.claim_id for item in snapshot] == [claim_id]

    duplicate = client.post("/v1/expense/claims", json=_payload("expense-idem-sql"))
    assert duplicate.json()["claim_id"] == claim_id
    await engine.dispose()


def test_expense_approval_ledger_and_unauthorized_decision() -> None:
    """验证报销审批台账及未授权决策对应的测试场景。"""
    container = build_memory_container()
    asyncio.run(
        container.rbac_repository.save_role(
            Role(
                role_id="finance-approver",
                tenant_id="tenant-1",
                name="finance_approver",
                permissions=["expense.claim.approve"],
            )
        )
    )
    asyncio.run(
        container.rbac_repository.save_assignment(
            RoleAssignment(
                assignment_id="finance-assignment",
                tenant_id="tenant-1",
                user_id="approver-1",
                role_id="finance-approver",
            )
        )
    )
    client = TestClient(create_platform_app(container))

    created = client.post(
        "/v1/expense/claims",
        json=_payload("expense-approval-1"),
    ).json()
    submitted = client.post(
        f"/v1/expense/claims/{created['claim_id']}/submit",
        json={"tenant_id": "tenant-1"},
    )
    assert submitted.status_code == 200

    denied = client.post(
        f"/v1/expense/claims/{created['claim_id']}/decision",
        json={
            "tenant_id": "tenant-1",
            "decided_by": "unassigned-user",
            "decision": "approve",
        },
    )
    assert denied.status_code == 403

    approved = client.post(
        f"/v1/expense/claims/{created['claim_id']}/decision",
        json={
            "tenant_id": "tenant-1",
            "decided_by": "approver-1",
            "decision": "approve",
            "reason": "receipts verified",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == ExpenseClaimStatus.APPROVED.value
    assert approved.json()["metadata"]["approval"]["decided_by"] == "approver-1"

    ledger = client.get("/v1/expense/ledger", params={"tenant_id": "tenant-1"}).json()
    assert ledger["total_amount_cents"] == 12800
    assert [claim["claim_id"] for claim in ledger["claims"]] == [created["claim_id"]]

    assert approved.json()["metadata"]["knowledge_indexed"] is True
    search = client.get(
        "/v1/expense/search",
        params={"tenant_id": "tenant-1", "query": "travel"},
    ).json()
    assert search["results"]
    assert search["results"][0]["metadata"]["claim_id"] == created["claim_id"]
    assert search["results"][0]["source_uri"] == f"expense://claims/{created['claim_id']}"
    isolated_search = client.get(
        "/v1/expense/search",
        params={"tenant_id": "tenant-2", "query": "travel"},
    ).json()
    assert isolated_search["results"] == []

    pending = asyncio.run(container.outbox_store.fetch_pending())
    assert [event.event_type for event in pending] == [
        "expense.claim.created.v1",
        "expense.claim.submitted.v1",
        "expense.claim.approved.v1",
    ]
