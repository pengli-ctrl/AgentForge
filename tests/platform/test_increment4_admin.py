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
    return TenantQuota(
        tenant_id=tenant_id,
        monthly_limit=100.0,
        warning_threshold=0.6,
        hard_limit=0.9,
        enabled=True,
    )


def _cost(tenant_id: str, amount: float) -> CostRecord:
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
    audit = MemoryAuditRepository()
    asyncio.run(_seed_events(audit))
    c = _memory_container(audit_repository=audit)
    return TestClient(create_platform_app(c))


async def _seed_events(repo) -> None:
    await repo.save(_event("t1", "read"))
    await repo.save(_event("t1", "write", actor_id="alice"))
    await repo.save(_event("t2", "write"))


def test_audit_endpoint_action_filter() -> None:
    tc = _admin_app()
    r = tc.get("/v1/audit", params={"tenant_id": "t1", "action": "write"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["events"]) == 1
    assert data["events"][0]["action"] == "write"


def test_audit_endpoint_admin_global() -> None:
    tc = _admin_app()
    r = tc.get("/v1/audit")
    assert r.status_code == 200
    assert len(r.json()["events"]) == 3


def test_audit_endpoint_pagination() -> None:
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
    tc = _admin_app()
    r = tc.get("/v1/console/audit", params={"action": "write"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["events"]) == 2
    assert {e["tenant_id"] for e in data["events"]} == {"t1", "t2"}


def test_console_tenants_admin_list() -> None:
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
    repo = MemoryConnectorRepository()
    asyncio.run(_seed_specs(repo))
    return repo


async def _seed_specs(repo) -> None:
    await repo.save_spec(_spec("c1", "t1", enabled=True))
    await repo.save_spec(_spec("c2", "t2", enabled=False))


def test_console_connectors_admin_list_and_toggle() -> None:
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
    repo = _seed_connectors()
    c = _memory_container()
    c.connector_repository = repo
    tc = TestClient(create_platform_app(c))
    r = tc.post("/v1/console/connectors/nope/enabled", json={"enabled": True})
    assert r.status_code == 404
