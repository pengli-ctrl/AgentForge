"""测试租户模块测试模块。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.domain.tenant_module import TenantModuleState
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.sqlalchemy_tenant_module_repository import (
    SQLAlchemyTenantModuleRepository,
)


def _expense_body(idempotency_key: str, tenant_id: str) -> dict[str, object]:
    """处理报销请求体。

    Args:
        idempotency_key: 幂等键，用于避免重复处理。
        tenant_id: 租户 ID，用于数据隔离。

    Returns:
        结构化结果字典。
    """
    return {
        "tenant_id": tenant_id,
        "applicant_id": "employee-1",
        "amount_cents": 9900,
        "expense_date": "2026-10-19",
        "category": "meal",
        "idempotency_key": idempotency_key,
    }


def test_tenant_module_override_blocks_only_target_tenant_and_module() -> None:
    """验证租户模块覆盖阻止目标租户及模块对应的测试场景。"""
    client = TestClient(create_platform_app())

    listed = client.get("/v1/admin/tenants/tenant-a/modules")
    assert listed.status_code == 200
    assert {item["module_name"] for item in listed.json()["modules"]} == {
        "support",
        "expense",
    }

    disabled = client.put(
        "/v1/admin/tenants/tenant-a/modules/expense",
        json={"enabled": False, "actor_id": "admin-1", "plan_name": "support-only"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    blocked = client.post(
        "/v1/expense/claims",
        json=_expense_body("tenant-a-expense", "tenant-a"),
    )
    assert blocked.status_code == 403

    support_still_works = client.post(
        "/v1/support/events/im",
        json={
            "tenant_id": "tenant-a",
            "source": "feishu",
            "message_id": "msg-after-expense-disable",
            "text": "How do I use this product?",
        },
    )
    assert support_still_works.status_code == 200

    other_tenant = client.post(
        "/v1/expense/claims",
        json=_expense_body("tenant-b-expense", "tenant-b"),
    )
    assert other_tenant.status_code == 200

    audit = client.get(
        "/v1/audit",
        params={"tenant_id": "tenant-a", "resource_id": "expense"},
    ).json()["events"]
    assert any(event["action"] == "tenant.module.disabled" for event in audit)

    unknown = client.put(
        "/v1/admin/tenants/tenant-a/modules/not-deployed",
        json={"enabled": True, "actor_id": "admin-1"},
    )
    assert unknown.status_code == 404


@pytest.mark.asyncio
async def test_sqlalchemy_tenant_module_repository_round_trip() -> None:
    """验证SQLAlchemy租户模块仓储轮次往返对应的测试场景。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = SQLAlchemyTenantModuleRepository(session_factory)
    state = TenantModuleState(
        tenant_id="tenant-sql",
        module_name="expense",
        enabled=False,
        plan_name="support-only",
    )
    await repository.save(state)
    loaded = await repository.get("tenant-sql", "expense")
    assert loaded is not None
    assert loaded.enabled is False
    assert loaded.plan_name == "support-only"
    assert len(await repository.list("tenant-sql")) == 1
    await engine.dispose()
