from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.application.report_service import ReportService
from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.cost import CostRecord
from agentforge.platform.domain.reporting import (
    ReportFormat,
    ReportRun,
    ReportType,
    ScheduledReport,
)
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.memory_audit_repository import MemoryAuditRepository
from agentforge.platform.infrastructure.memory_cost_repository import MemoryCostRepository
from agentforge.platform.infrastructure.memory_regression_repository import (
    MemoryRegressionRepository,
)
from agentforge.platform.infrastructure.memory_report_run_repository import (
    MemoryReportRunRepository,
)
from agentforge.platform.infrastructure.memory_scheduled_report_repository import (
    MemoryScheduledReportRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_report_run_repository import (
    SQLAlchemyReportRunRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_scheduled_report_repository import (
    SQLAlchemyScheduledReportRepository,
)
from agentforge.platform.runtime import ServiceContainer


def _cost(tenant_id: str, amount: float, days_ago: int = 0) -> CostRecord:
    return CostRecord(
        tenant_id=tenant_id,
        task_id=f"task-{tenant_id}-{amount}-{days_ago}",
        model_name="gpt",
        provider="openai",
        input_tokens=10,
        output_tokens=5,
        amount=amount,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


def _event(tenant_id: str, action: str) -> AuditEvent:
    return AuditEvent(
        event_id=f"ev-{tenant_id}-{action}",
        tenant_id=tenant_id,
        action=action,
        resource_type="ticket",
        resource_id=f"r-{tenant_id}",
        actor_type="user",
        actor_id="alice",
        occurred_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )


def _sched(report_id: str, tenant_id: str, *, next_in_hours: int = -1) -> ScheduledReport:
    return ScheduledReport(
        report_id=report_id,
        tenant_id=tenant_id,
        report_type=ReportType.COST,
        cadence="daily",
        enabled=True,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        last_run_at=None,
        next_run_at=datetime.now(timezone.utc) + timedelta(hours=next_in_hours),
    )


# --- repository tests ---


@pytest.mark.asyncio
async def test_memory_schedule_repository_crud_and_due() -> None:
    repo = MemoryScheduledReportRepository()
    await repo.save(_sched("r1", "t1", next_in_hours=-2))
    await repo.save(_sched("r2", "t2", next_in_hours=5))

    assert await repo.get("r1") is not None
    assert len(await repo.list_schedules(tenant_id="t1")) == 1
    assert len(await repo.list_schedules()) == 2

    due = await repo.list_due()
    assert len(due) == 1 and due[0].report_id == "r1"

    await repo.delete("r1")
    assert await repo.get("r1") is None
    assert len(await repo.list_schedules()) == 1


@pytest.mark.asyncio
async def test_sqlalchemy_schedule_repository_crud_and_due() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repo = SQLAlchemyScheduledReportRepository(session_factory)
    await repo.save(_sched("r1", "t1", next_in_hours=-2))
    await repo.save(_sched("r2", "t2", next_in_hours=5))

    assert (await repo.get("r2")).tenant_id == "t2"
    assert len(await repo.list_schedules(tenant_id="t1")) == 1
    due = await repo.list_due()
    assert len(due) == 1 and due[0].report_id == "r1"

    await repo.delete("r2")
    assert await repo.get("r2") is None


# --- service tests ---


def _service(seed_audit: bool = True) -> ReportService:
    cost = MemoryCostRepository()
    cost.records.append(_cost("t1", 1.5, days_ago=1))
    cost.records.append(_cost("t1", 0.5, days_ago=0))
    audit = MemoryAuditRepository()
    if seed_audit:
        _save_sync(audit, _event("t1", "read"))
    return ReportService(
        cost_repository=cost,
        audit_repository=audit,
        regression_repository=MemoryRegressionRepository(),
        schedule_repository=MemoryScheduledReportRepository(),
        run_repository=MemoryReportRunRepository(),
    )


def _save_sync(repo, event: AuditEvent) -> None:
    # MemoryAuditRepository.save only appends to .events; call it directly to
    # avoid an asyncio.run inside a running test event loop.
    repo.events.append(event)


@pytest.mark.asyncio
async def test_report_service_generate_json_cost() -> None:
    svc = _service(seed_audit=False)
    report = await svc.generate(report_type=ReportType.COST, tenant_id="t1", fmt=ReportFormat.JSON)
    assert report.summary["total_amount"] == pytest.approx(2.0, rel=1e-3)
    assert report.summary["total_requests"] == 2
    payload = json.loads(report.to_json())
    assert payload["report_type"] == "cost"
    assert len(payload["rows"]) in (1, 2)


@pytest.mark.asyncio
async def test_report_service_generate_csv_cost() -> None:
    svc = _service(seed_audit=False)
    report = await svc.generate(report_type=ReportType.COST, tenant_id="t1", fmt=ReportFormat.CSV)
    reader = csv.DictReader(io.StringIO(report.to_csv()))
    rows = list(reader)
    assert len(rows) >= 1
    assert set(rows[0].keys()) >= {"date", "amount", "request_count"}


@pytest.mark.asyncio
async def test_report_service_generate_audit() -> None:
    svc = _service(seed_audit=True)
    report = await svc.generate(report_type=ReportType.AUDIT, tenant_id="t1")
    assert report.summary["event_count"] >= 1
    assert report.rows[0]["action"] == "read"


@pytest.mark.asyncio
async def test_report_service_schedule_and_run_due_idempotent() -> None:
    svc = _service()
    sched = await svc.schedule(tenant_id="t1", report_type=ReportType.AUDIT, cadence="daily")
    # force it due
    sched.next_run_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await svc._schedules.save(sched)

    result = await svc.run_due()
    assert result["generated"] == 1
    assert result["reports"][0]["report_type"] == "audit"

    # second run: schedule advanced, not due anymore -> 0
    again = await svc.run_due()
    assert again["generated"] == 0


@pytest.mark.asyncio
async def test_report_run_repository_memory_crud_and_list() -> None:
    repo = MemoryReportRunRepository()
    report = await _service().generate(report_type=ReportType.COST, tenant_id="t1")
    run = ReportRun.from_operations(report)
    await repo.save(run)
    assert (await repo.get(run.run_id)).tenant_id == "t1"
    listed = await repo.list(tenant_id="t1")
    assert len(listed) == 1 and listed[0].report_type.value == "cost"
    assert await repo.list(report_type="audit") == []


@pytest.mark.asyncio
async def test_report_run_repository_sqlalchemy_crud_and_list() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repo = SQLAlchemyReportRunRepository(session_factory)
    report = await _service().generate(report_type=ReportType.COST, tenant_id="t1")
    run = ReportRun.from_operations(report)
    await repo.save(run)
    fetched = await repo.get(run.run_id)
    assert fetched is not None and fetched.summary["total_amount"] == pytest.approx(2.0, rel=1e-3)
    assert len(await repo.list(tenant_id="t1")) == 1
    assert await repo.list(report_type="crisis") == []


@pytest.mark.asyncio
async def test_report_service_persists_runs_and_history() -> None:
    svc = _service(seed_audit=False)
    await svc.generate(report_type=ReportType.COST, tenant_id="t1", fmt=ReportFormat.CSV)
    await svc.generate(report_type=ReportType.AUDIT, tenant_id="t1")
    runs = await svc.list_runs(tenant_id="t1")
    assert len(runs) == 2
    assert {r["report_type"] for r in runs} == {"cost", "audit"}
    assert all("format" in r and "rows" in r for r in runs)
    cost_runs = await svc.list_runs(tenant_id="t1", report_type="cost")
    assert len(cost_runs) == 1 and cost_runs[0]["format"] == "csv"


# --- endpoint tests ---


def _memory_container(**overrides) -> ServiceContainer:
    cost = MemoryCostRepository()
    cost.records.append(_cost("t1", 1.0))
    audit = MemoryAuditRepository()
    _save_sync(audit, _event("t1", "read"))
    defaults = dict(
        repository=None,
        classifier=None,
        knowledge_repository=None,
        model_gateway=None,
        cost_repository=cost,
        audit_repository=audit,
    )
    defaults.update(overrides)
    return ServiceContainer(**defaults)


def _app() -> TestClient:
    return TestClient(create_platform_app(_memory_container()))


def test_export_report_json() -> None:
    tc = _app()
    r = tc.get("/v1/console/reports/export", params={"report_type": "cost", "tenant_id": "t1"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    data = json.loads(r.text)
    assert data["report_type"] == "cost"
    assert data["tenant_id"] == "t1"


def test_export_report_csv() -> None:
    tc = _app()
    r = tc.get(
        "/v1/console/reports/export",
        params={"report_type": "cost", "tenant_id": "t1", "format": "csv"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "amount" in r.text


def test_export_report_invalid_type() -> None:
    tc = _app()
    r = tc.get("/v1/console/reports/export", params={"report_type": "bogus", "tenant_id": "t1"})
    assert r.status_code == 400


def test_schedule_lifecycle() -> None:
    tc = _app()
    create = tc.post(
        "/v1/console/reports/schedule",
        json={"tenant_id": "t1", "report_type": "quality", "cadence": "daily"},
    )
    assert create.status_code == 200
    body = create.json()
    assert body["report_type"] == "quality"
    rid = body["report_id"]

    listing = tc.get("/v1/console/reports/schedules")
    assert listing.status_code == 200
    assert any(s["report_id"] == rid for s in listing.json()["schedules"])

    listing_t = tc.get("/v1/console/reports/schedules", params={"tenant_id": "t1"})
    assert all(s["tenant_id"] == "t1" for s in listing_t.json()["schedules"])


def test_run_due_endpoint() -> None:
    tc = _app()
    created = tc.post(
        "/v1/console/reports/schedule",
        json={"tenant_id": "t1", "report_type": "cost", "cadence": "daily"},
    ).json()
    rid = created["report_id"]

    # force due via direct service is awkward through HTTP; instead assert the
    # endpoint returns 200 and reports metadata shape for any due schedule.
    r = tc.post("/v1/console/reports/run-due")
    assert r.status_code == 200
    data = r.json()
    assert "generated" in data and "reports" in data

    deleted = tc.delete(f"/v1/console/reports/schedule/{rid}")
    assert deleted.status_code == 200
    listing = tc.get("/v1/console/reports/schedules", params={"tenant_id": "t1"})
    assert all(s["report_id"] != rid for s in listing.json()["schedules"])


def test_report_runs_history_and_retrieve() -> None:
    tc = _app()
    # export persists a run; capture its run_id
    exported = tc.get(
        "/v1/console/reports/export",
        params={"report_type": "cost", "tenant_id": "t1", "format": "csv"},
    )
    assert exported.status_code == 200
    listed = tc.get("/v1/console/reports/runs", params={"tenant_id": "t1"})
    assert listed.status_code == 200
    runs = listed.json()["runs"]
    assert len(runs) >= 1
    run_id = runs[0]["run_id"]
    assert runs[0]["format"] == "csv" and runs[0]["report_type"] == "cost"

    fetched = tc.get(f"/v1/console/reports/runs/{run_id}")
    assert fetched.status_code == 200
    assert fetched.json()["report_type"] == "cost"

    fetched_csv = tc.get(f"/v1/console/reports/runs/{run_id}?format=csv")
    assert fetched_csv.status_code == 200
    assert fetched_csv.headers["content-type"].startswith("text/csv")
    assert "amount" in fetched_csv.text


def test_report_runs_history_filter_and_missing() -> None:
    tc = _app()
    filtered = tc.get(
        "/v1/console/reports/runs", params={"tenant_id": "t1", "report_type": "audit"}
    )
    assert filtered.status_code == 200
    assert filtered.json()["runs"] == []
    missing = tc.get("/v1/console/reports/runs/nope")
    assert missing.status_code == 404
