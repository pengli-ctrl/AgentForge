"""测试模块。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.application.saas_plans import PlanCatalog, PlanDefinition
from agentforge.platform.application.usage_metering_service import UsageMeteringService
from agentforge.platform.domain.tenant_account import TenantAccount, TenantStatus
from agentforge.platform.domain.usage import UsageMetric
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.memory_audit_repository import MemoryAuditRepository
from agentforge.platform.infrastructure.memory_tenant_account_repository import (
    MemoryTenantAccountRepository,
)
from agentforge.platform.infrastructure.memory_usage_repository import MemoryUsageRepository
from agentforge.platform.infrastructure.sqlalchemy_tenant_account_repository import (
    SQLAlchemyTenantAccountRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_usage_repository import SQLAlchemyUsageRepository


def _provision(client: TestClient, tenant_id: str, plan_name: str = "starter") -> object:
    """开通数据。

    Args:
        client: 客户端实例。
        tenant_id: 租户 ID，用于数据隔离。
        plan_name: 套餐名称。

    Returns:
        对象结果。
    """
    return client.post(
        "/v1/admin/tenants",
        json={
            "tenant_id": tenant_id,
            "name": f"Tenant {tenant_id}",
            "plan_name": plan_name,
            "actor_id": "ops-admin",
        },
    )


def test_tenant_lifecycle_plan_switch_usage_billing_and_operations() -> None:
    """验证租户生命周期计划用量及操作对应的测试场景。"""
    client = TestClient(create_platform_app(load_plugins=False))

    plans = client.get("/v1/admin/plans")
    assert plans.status_code == 200
    assert {"starter", "professional", "enterprise", "private"} <= {
        plan["name"] for plan in plans.json()["plans"]
    }

    created = _provision(client, "tenant-saas")
    assert created.status_code == 200
    assert created.json()["status"] == "active"
    assert created.json()["plan"]["modules"] == ["support"]

    support = client.post(
        "/v1/support/events/im",
        json={
            "tenant_id": "tenant-saas",
            "source": "feishu",
            "message_id": "saas-support-1",
            "text": "How do I use this product?",
        },
    )
    assert support.status_code == 200
    expense = client.post(
        "/v1/expense/claims",
        json={
            "tenant_id": "tenant-saas",
            "applicant_id": "employee-1",
            "amount_cents": 100,
            "expense_date": "2026-10-19",
            "category": "meal",
            "idempotency_key": "saas-expense-blocked",
        },
    )
    assert expense.status_code == 403

    usage = client.post(
        "/v1/admin/tenants/tenant-saas/usage",
        json={
            "metric": "ocr_pages",
            "quantity": 60,
            "source": "ocr-worker",
            "idempotency_key": "ocr-batch-1",
        },
    )
    assert usage.status_code == 200
    assert usage.json()["accepted"] is True
    assert usage.json()["overage"] == 10
    duplicate = client.post(
        "/v1/admin/tenants/tenant-saas/usage",
        json={
            "metric": "ocr_pages",
            "quantity": 60,
            "source": "ocr-worker",
            "idempotency_key": "ocr-batch-1",
        },
    )
    assert duplicate.json()["duplicate"] is True
    summary = client.get("/v1/admin/tenants/tenant-saas/usage")
    assert summary.json()["metrics"]["ocr_pages"]["used"] == 60
    assert summary.json()["metrics"]["ocr_pages"]["overage"] == 10
    alerts = client.get("/v1/admin/tenants/tenant-saas/usage/alerts")
    assert alerts.json()["alerts"][0]["status"] == "critical"
    export = client.get("/v1/admin/tenants/tenant-saas/usage/export")
    assert export.status_code == 200
    assert "ocr_pages,60,50" in export.text
    invoice = client.get("/v1/admin/tenants/tenant-saas/invoice")
    assert invoice.status_code == 200
    assert invoice.json()["plan_name"] == "starter"
    assert invoice.json()["total_cents"] > invoice.json()["base_fee_cents"]

    changed = client.post(
        "/v1/admin/tenants/tenant-saas/plan",
        json={"plan_name": "professional", "actor_id": "ops-admin"},
    )
    assert changed.status_code == 200
    assert changed.json()["plan_name"] == "professional"
    expense_after_upgrade = client.post(
        "/v1/expense/claims",
        json={
            "tenant_id": "tenant-saas",
            "applicant_id": "employee-1",
            "amount_cents": 100,
            "expense_date": "2026-10-19",
            "category": "meal",
            "idempotency_key": "saas-expense-enabled",
        },
    )
    assert expense_after_upgrade.status_code == 200

    suspended = client.post(
        "/v1/admin/tenants/tenant-saas/suspend",
        json={"actor_id": "ops-admin", "reason": "payment overdue"},
    )
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"
    blocked = client.post(
        "/v1/support/events/im",
        json={
            "tenant_id": "tenant-saas",
            "source": "feishu",
            "message_id": "saas-support-suspended",
            "text": "hello",
        },
    )
    assert blocked.status_code == 403
    resumed = client.post(
        "/v1/admin/tenants/tenant-saas/resume",
        json={"actor_id": "ops-admin", "reason": "payment received"},
    )
    assert resumed.json()["status"] == "active"

    operations = client.get("/v1/admin/operations/overview")
    assert operations.status_code == 200
    assert operations.json()["tenant_count"] == 1
    assert operations.json()["usage_totals"]["ocr_pages"] == 60

    cancelled = client.post(
        "/v1/admin/tenants/tenant-saas/cancel",
        json={
            "actor_id": "ops-admin",
            "reason": "customer churned",
            "confirmation": "tenant-saas",
        },
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    after_cancel = client.post(
        "/v1/support/events/im",
        json={
            "tenant_id": "tenant-saas",
            "source": "feishu",
            "message_id": "saas-support-cancelled",
            "text": "hello",
        },
    )
    assert after_cancel.status_code == 403


@pytest.mark.asyncio
async def test_blocking_overage_policy_does_not_record_usage() -> None:
    """验证策略会不记录用量对应的测试场景。"""
    plans = PlanCatalog(
        [
            PlanDefinition(
                name="blocked",
                display_name="Blocked",
                modules=("support",),
                metric_limits={UsageMetric.OCR_PAGES: 10},
                overage_policy="block",
            )
        ],
        default_plan="blocked",
    )
    accounts = MemoryTenantAccountRepository()
    await accounts.save(
        TenantAccount(
            tenant_id="tenant-blocked",
            name="Blocked",
            plan_name="blocked",
            status=TenantStatus.ACTIVE,
        )
    )
    usage_repository = MemoryUsageRepository()
    audit = MemoryAuditRepository()
    service = UsageMeteringService(usage_repository, accounts, plans, audit=audit)

    first = await service.record(
        tenant_id="tenant-blocked",
        metric=UsageMetric.OCR_PAGES,
        quantity=8,
    )
    blocked = await service.record(
        tenant_id="tenant-blocked",
        metric=UsageMetric.OCR_PAGES,
        quantity=5,
    )
    summary = await service.summary("tenant-blocked")

    assert first.accepted is True
    assert blocked.accepted is False
    assert blocked.blocked is True
    assert summary["metrics"]["ocr_pages"]["used"] == 8
    events = await audit.list_events("tenant-blocked")
    assert any(event.action == "tenant.usage.blocked" for event in events)


@pytest.mark.asyncio
async def test_sqlalchemy_account_and_usage_repositories_round_trip() -> None:
    """验证SQLAlchemy及用量轮次往返对应的测试场景。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    accounts = SQLAlchemyTenantAccountRepository(session_factory)
    usage = SQLAlchemyUsageRepository(session_factory)
    account = TenantAccount(
        tenant_id="tenant-sql-saas",
        name="SQL SaaS",
        plan_name="starter",
        status=TenantStatus.ACTIVE,
    )
    await accounts.save(account)
    loaded = await accounts.get("tenant-sql-saas")
    assert loaded is not None and loaded.status == TenantStatus.ACTIVE
    now = datetime.now(timezone.utc)
    record = type(
        "Record",
        (),
        {
            "record_id": "usage-sql-1",
            "tenant_id": "tenant-sql-saas",
            "metric": UsageMetric.MODEL_TOKENS,
            "quantity": 1234,
            "source": "test",
            "idempotency_key": "usage-key-1",
            "occurred_at": now,
            "metadata": {},
        },
    )()
    assert await usage.add(record) is True
    assert await usage.add(record) is False
    assert (
        await usage.total(
            "tenant-sql-saas",
            UsageMetric.MODEL_TOKENS,
            start=now - timedelta(days=1),
            end=now + timedelta(days=1),
        )
        >= 1234
    )
    await engine.dispose()
