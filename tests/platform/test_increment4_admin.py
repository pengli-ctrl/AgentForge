"""AgentForge 平台测试层：test_increment4_admin。

本测试模块验证 test_increment4_admin 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_memory_audit_query_filters_and_cursor、test_sqlalchemy_audit_query_filters_and_cursor、test_audit_endpoint_action_filter、test_audit_endpoint_admin_global、test_audit_endpoint_pagination、test_console_audit_admin_query、test_console_tenants_admin_list、test_console_connectors_admin_list_and_toggle。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.connector import ConnectorSpec
from agentforge.platform.domain.cost import CostRecord
from agentforge.platform.domain.tenant_quota import TenantQuota
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.memory_audit_repository import MemoryAuditRepository
from agentforge.platform.infrastructure.memory_connector_repository import (
    MemoryConnectorRepository,
)
from agentforge.platform.infrastructure.memory_cost_repository import MemoryCostRepository
from agentforge.platform.infrastructure.memory_tenant_quota_repository import (
    MemoryTenantQuotaRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_audit_repository import (
    SQLAlchemyAuditRepository,
)
from agentforge.platform.runtime import ServiceContainer


def _event(
    tenant_id: str,
    action: str,
    *,
    actor_id: str = "mallory",
    resource_id: str = "r1",
    resource_type: str = "ticket",
    offset_minutes: int = 0,
) -> AuditEvent:
    """执行 _event 对应的逻辑，并返回处理结果。

    Args:
        tenant_id: str，调用方传入的 tenant_id 参数。
        action: str，调用方传入的 action 参数。
        actor_id: str，调用方传入的 actor_id 参数。
        resource_id: str，调用方传入的 resource_id 参数。
        resource_type: str，调用方传入的 resource_type 参数。
        offset_minutes: int，调用方传入的 offset_minutes 参数。

    Returns:
        AuditEvent，函数执行后的结果。
    """
    return AuditEvent(
        event_id=f"ev-{tenant_id}-{action}-{offset_minutes}",
        tenant_id=tenant_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_type="user",
        actor_id=actor_id,
        occurred_at=datetime.now(timezone.utc) - timedelta(minutes=offset_minutes),
    )


def _spec(connector_id: str, tenant_id: str, enabled: bool = True) -> ConnectorSpec:
    """执行 _spec 对应的逻辑，并返回处理结果。

    Args:
        connector_id: str，调用方传入的 connector_id 参数。
        tenant_id: str，调用方传入的 tenant_id 参数。
        enabled: bool，调用方传入的 enabled 参数。

    Returns:
        ConnectorSpec，函数执行后的结果。
    """
    return ConnectorSpec(
        connector_id=connector_id,
        tenant_id=tenant_id,
        name=connector_id,
        kind="http",
        endpoint="https://example.invalid/cb",
        allowed_actions=["send"],
        enabled=enabled,
    )


def _quota(tenant_id: str) -> TenantQuota:
    """执行 _quota 对应的逻辑，并返回处理结果。

    Args:
        tenant_id: str，调用方传入的 tenant_id 参数。

    Returns:
        TenantQuota，函数执行后的结果。
    """
    return TenantQuota(
        tenant_id=tenant_id,
        monthly_limit=100.0,
        warning_threshold=0.6,
        hard_limit=0.9,
        enabled=True,
    )


def _cost(tenant_id: str, amount: float) -> CostRecord:
    """执行 _cost 对应的逻辑，并返回处理结果。

    Args:
        tenant_id: str，调用方传入的 tenant_id 参数。
        amount: float，调用方传入的 amount 参数。

    Returns:
        CostRecord，函数执行后的结果。
    """
    return CostRecord(
        tenant_id=tenant_id,
        task_id="task",
        model_name="gpt",
        provider="openai",
        input_tokens=1,
        output_tokens=1,
        amount=amount,
    )


def _memory_container(**overrides) -> ServiceContainer:
    """执行 _memory_container 对应的逻辑，并返回处理结果。

    Args:
        **overrides: Any，调用方传入的 **overrides 参数。

    Returns:
        ServiceContainer，函数执行后的结果。
    """
    defaults = dict(
        repository=None,
        classifier=None,
        knowledge_repository=None,
        model_gateway=None,
        cost_repository=MemoryCostRepository(),
        outbox_store=None,
        authenticator=None,
    )
    defaults.update(overrides)
    return ServiceContainer(**defaults)


async def test_memory_audit_query_filters_and_cursor() -> None:
    """验证 memory_audit_query_filters_and_cursor 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    repo = MemoryAuditRepository()
    for ev in (
        _event("t1", "read", offset_minutes=10),
        _event("t1", "write", actor_id="alice", offset_minutes=5),
        _event("t1", "write", actor_id="mallory", resource_id="r2", offset_minutes=1),
        _event("t2", "write", offset_minutes=2),
    ):
        await repo.save(ev)

    out, _ = await repo.query_events(tenant_id="t1", action="write")
    assert len(out) == 2
    assert {e.actor_id for e in out} == {"alice", "mallory"}

    out, _ = await repo.query_events(tenant_id="t1", actor_id="alice")
    assert len(out) == 1 and out[0].action == "write"

    out, _ = await repo.query_events()
    assert len(out) == 4

    page1, cur = await repo.query_events(tenant_id="t1", limit=2)
    assert len(page1) == 2 and cur is not None
    page2, cur2 = await repo.query_events(tenant_id="t1", limit=2, cursor=cur)
    assert len(page2) == 1 and cur2 is None
    ids = {e.event_id for e in page1 + page2}
    assert ids == {"ev-t1-read-10", "ev-t1-write-5", "ev-t1-write-1"}


@pytest.mark.asyncio
async def test_sqlalchemy_audit_query_filters_and_cursor() -> None:
    """验证 sqlalchemy_audit_query_filters_and_cursor 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repo = SQLAlchemyAuditRepository(session_factory)
    await repo.save(_event("t1", "read", offset_minutes=10))
    await repo.save(_event("t1", "write", actor_id="alice", offset_minutes=5))
    await repo.save(_event("t1", "write", actor_id="mallory", resource_id="r2", offset_minutes=1))

    out, _ = await repo.query_events(tenant_id="t1", action="write")
    assert len(out) == 2
    assert {e.actor_id for e in out} == {"alice", "mallory"}

    page1, cur = await repo.query_events(tenant_id="t1", limit=2)
    assert len(page1) == 2 and cur is not None
    page2, cur2 = await repo.query_events(tenant_id="t1", limit=2, cursor=cur)
    assert len(page2) == 1 and cur2 is None


def _admin_app() -> TestClient:
    """执行 _admin_app 对应的逻辑，并返回处理结果。

    Returns:
        TestClient，函数执行后的结果。
    """
    audit = MemoryAuditRepository()
    asyncio.run(_seed_events(audit))
    c = _memory_container(audit_repository=audit)
    return TestClient(create_platform_app(c))


async def _seed_events(repo) -> None:
    """执行 _seed_events 对应的逻辑，并返回处理结果。

    Args:
        repo: Any，调用方传入的 repo 参数。

    Returns:
        None，函数执行后的结果。
    """
    await repo.save(_event("t1", "read"))
    await repo.save(_event("t1", "write", actor_id="alice"))
    await repo.save(_event("t2", "write"))


def test_audit_endpoint_action_filter() -> None:
    """验证 audit_endpoint_action_filter 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    tc = _admin_app()
    r = tc.get("/v1/audit", params={"tenant_id": "t1", "action": "write"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["events"]) == 1
    assert data["events"][0]["action"] == "write"


def test_audit_endpoint_admin_global() -> None:
    """验证 audit_endpoint_admin_global 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    tc = _admin_app()
    r = tc.get("/v1/audit")
    assert r.status_code == 200
    assert len(r.json()["events"]) == 3


def test_audit_endpoint_pagination() -> None:
    """验证 audit_endpoint_pagination 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    tc = _admin_app()
    r = tc.get("/v1/audit", params={"tenant_id": "t1", "limit": 1})
    assert r.status_code == 200
    data = r.json()
    assert len(data["events"]) == 1
    assert data["next_cursor"] is not None
    r2 = tc.get("/v1/audit", params={"tenant_id": "t1", "limit": 1, "cursor": data["next_cursor"]})
    assert r2.status_code == 200
    assert len(r2.json()["events"]) == 1
    assert r2.json()["next_cursor"] is None


def test_console_audit_admin_query() -> None:
    """验证 console_audit_admin_query 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    tc = _admin_app()
    r = tc.get("/v1/console/audit", params={"action": "write"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["events"]) == 2
    assert {e["tenant_id"] for e in data["events"]} == {"t1", "t2"}


def test_console_tenants_admin_list() -> None:
    """验证 console_tenants_admin_list 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    quota = MemoryTenantQuotaRepository()
    asyncio.run(quota.upsert(_quota("t1")))
    cost = MemoryCostRepository()
    cost.records.append(_cost("t1", 12.0))
    cost.records.append(_cost("t2", 3.0))
    c = _memory_container(
        cost_repository=cost,
        tenant_quota_repository=quota,
    )
    tc = TestClient(create_platform_app(c))
    r = tc.get("/v1/console/tenants")
    assert r.status_code == 200
    by = {row["tenant_id"]: row for row in r.json()["tenants"]}
    assert set(by) == {"t1", "t2"}
    assert by["t1"]["quota"]["configured"] is True
    assert by["t1"]["used"] == 12.0
    assert by["t2"]["quota"]["configured"] is False


def _seed_connectors() -> MemoryConnectorRepository:
    """执行 _seed_connectors 对应的逻辑，并返回处理结果。

    Returns:
        MemoryConnectorRepository，函数执行后的结果。
    """
    repo = MemoryConnectorRepository()
    asyncio.run(_seed_specs(repo))
    return repo


async def _seed_specs(repo) -> None:
    """执行 _seed_specs 对应的逻辑，并返回处理结果。

    Args:
        repo: Any，调用方传入的 repo 参数。

    Returns:
        None，函数执行后的结果。
    """
    await repo.save_spec(_spec("c1", "t1", enabled=True))
    await repo.save_spec(_spec("c2", "t2", enabled=False))


def test_console_connectors_admin_list_and_toggle() -> None:
    """验证 console_connectors_admin_list_and_toggle 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    repo = _seed_connectors()
    c = _memory_container()
    c.connector_repository = repo
    tc = TestClient(create_platform_app(c))

    r = tc.get("/v1/console/connectors")
    assert r.status_code == 200
    conns = r.json()["connectors"]
    assert {x["connector_id"] for x in conns} == {"c1", "c2"}
    c1 = next(x for x in conns if x["connector_id"] == "c1")
    assert c1["enabled"] is True

    r2 = tc.post("/v1/console/connectors/c1/enabled", json={"enabled": False})
    assert r2.status_code == 200
    assert r2.json()["enabled"] is False

    r3 = tc.get("/v1/console/connectors")
    c1_after = next(x for x in r3.json()["connectors"] if x["connector_id"] == "c1")
    assert c1_after["enabled"] is False


def test_console_connector_toggle_missing_404() -> None:
    """验证 console_connector_toggle_missing_404 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    repo = _seed_connectors()
    c = _memory_container()
    c.connector_repository = repo
    tc = TestClient(create_platform_app(c))
    r = tc.post("/v1/console/connectors/nope/enabled", json={"enabled": True})
    assert r.status_code == 404
