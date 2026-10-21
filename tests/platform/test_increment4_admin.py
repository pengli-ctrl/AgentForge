"""管理测试模块。

本测试模块验证 test_increment4_admin 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_memory_audit_query_filters_and_cursor、test_sqlalchemy_audit_query_filters_and_cursor、t
    est_audit_endpoint_action_filter、test_audit_endpoint_admin_global、test_audit_endpoint_pagina
    tion、test_console_audit_admin_query、test_console_tenants_admin_list、test_console_connectors_
    admin_list_and_toggle。
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
from agentforge.platform.infrastructure.memory_connector_repository import MemoryConnectorRepository
from agentforge.platform.infrastructure.memory_cost_repository import MemoryCostRepository
from agentforge.platform.infrastructure.memory_tenant_quota_repository import (
    MemoryTenantQuotaRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_audit_repository import SQLAlchemyAuditRepository
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
    """处理事件。

    Args:
        tenant_id: 租户 ID，用于数据隔离。
        action: 待执行动作名称。
        actor_id: 执行操作的参与者 ID。
        resource_id: 资源 ID。
        resource_type: 资源类型。
        offset_minutes: 偏移。

    Returns:
        审计事件结果。
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
    """处理规格。

    Args:
        connector_id: 连接器 ID。
        tenant_id: 租户 ID，用于数据隔离。
        enabled: 启用。

    Returns:
        连接器规格结果。
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
    """处理配额。

    Args:
        tenant_id: 租户 ID，用于数据隔离。

    Returns:
        租户配额结果。
    """
    return TenantQuota(
        tenant_id=tenant_id,
        monthly_limit=100.0,
        warning_threshold=0.6,
        hard_limit=0.9,
        enabled=True,
    )


def _cost(tenant_id: str, amount: float) -> CostRecord:
    """处理成本。

    Args:
        tenant_id: 租户 ID，用于数据隔离。
        amount: 金额。

    Returns:
        成本记录结果。
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
    """处理记忆容器。

    Args:
        overrides: 配置覆盖项。

    Returns:
        服务容器结果。
    """
    defaults = dict(
        knowledge_repository=None,
        model_gateway=None,
        cost_repository=MemoryCostRepository(),
        outbox_store=None,
        authenticator=None,
    )
    defaults.update(overrides)
    return ServiceContainer(**defaults)


async def test_memory_audit_query_filters_and_cursor() -> None:
    """验证记忆审计查询筛选条件及游标对应的测试场景。"""
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
    """验证SQLAlchemy审计查询筛选条件及游标对应的测试场景。"""
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
    """处理管理应用。

    Returns:
        测试客户端结果。
    """
    audit = MemoryAuditRepository()
    asyncio.run(_seed_events(audit))
    c = _memory_container(audit_repository=audit)
    return TestClient(create_platform_app(c))


async def _seed_events(repo) -> None:
    """初始化事件。

    Args:
        repo: 仓储。
    """
    await repo.save(_event("t1", "read"))
    await repo.save(_event("t1", "write", actor_id="alice"))
    await repo.save(_event("t2", "write"))


def test_audit_endpoint_action_filter() -> None:
    """验证审计端点操作过滤对应的测试场景。"""
    tc = _admin_app()
    r = tc.get("/v1/audit", params={"tenant_id": "t1", "action": "write"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["events"]) == 1
    assert data["events"][0]["action"] == "write"


def test_audit_endpoint_admin_global() -> None:
    """验证审计端点管理全局对应的测试场景。"""
    tc = _admin_app()
    r = tc.get("/v1/audit")
    assert r.status_code == 200
    assert len(r.json()["events"]) == 3


def test_audit_endpoint_pagination() -> None:
    """验证审计端点分页对应的测试场景。"""
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
    """验证控制台审计管理查询对应的测试场景。"""
    tc = _admin_app()
    r = tc.get("/v1/console/audit", params={"action": "write"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["events"]) == 2
    assert {e["tenant_id"] for e in data["events"]} == {"t1", "t2"}


def test_console_tenants_admin_list() -> None:
    """验证控制台租户管理查询对应的测试场景。"""
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
    """初始化连接器。

    Returns:
        记忆连接器仓储结果。
    """
    repo = MemoryConnectorRepository()
    asyncio.run(_seed_specs(repo))
    return repo


async def _seed_specs(repo) -> None:
    """初始化规格。

    Args:
        repo: 仓储。
    """
    await repo.save_spec(_spec("c1", "t1", enabled=True))
    await repo.save_spec(_spec("c2", "t2", enabled=False))


def test_console_connectors_admin_list_and_toggle() -> None:
    """验证控制台连接器管理查询及切换对应的测试场景。"""
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
    """验证控制台连接器切换缺失资源不存在对应的测试场景。"""
    repo = _seed_connectors()
    c = _memory_container()
    c.connector_repository = repo
    tc = TestClient(create_platform_app(c))
    r = tc.post("/v1/console/connectors/nope/enabled", json={"enabled": True})
    assert r.status_code == 404
