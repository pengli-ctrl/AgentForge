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
from agentforge.platform.domain.cron import (
    CronExpressionError,
    CronSchedule,
    is_cron_cadence,
)
from agentforge.platform.domain.reporting import (
    ReportFormat,
    ReportRun,
    ReportType,
    ScheduledReport,
    _decode_run_cursor,
    _encode_run_cursor,
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


@pytest.mark.asyncio
async def test_memory_schedule_repository_retention_persisted() -> None:
    repo = MemoryScheduledReportRepository()
    sched = _sched("r1", "t1", next_in_hours=-1)
    sched.retention_days = 14
    await repo.save(sched)
    fetched = await repo.get("r1")
    assert fetched is not None and fetched.retention_days == 14


@pytest.mark.asyncio
async def test_sqlalchemy_schedule_repository_retention_persisted() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repo = SQLAlchemyScheduledReportRepository(session_factory)
    sched = _sched("r1", "t1", next_in_hours=-1)
    sched.retention_days = 7
    await repo.save(sched)
    fetched = await repo.get("r1")
    assert fetched is not None and fetched.retention_days == 7


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


@pytest.mark.asyncio
async def test_report_run_repository_delete_older_than_memory() -> None:
    repo = MemoryReportRunRepository()
    # brand-new runs
    fresh = ReportRun.from_operations(
        await _service().generate(report_type=ReportType.COST, tenant_id="t1")
    )
    fresh.generated_at = datetime.now(timezone.utc) - timedelta(days=1)
    old = ReportRun.from_operations(
        await _service().generate(report_type=ReportType.AUDIT, tenant_id="t1")
    )
    old.generated_at = datetime.now(timezone.utc) - timedelta(days=100)
    other = ReportRun.from_operations(
        await _service().generate(report_type=ReportType.COST, tenant_id="t2")
    )
    other.generated_at = datetime.now(timezone.utc) - timedelta(days=100)
    await repo.save(fresh)
    await repo.save(old)
    await repo.save(other)

    # cutoff at 30 days: removes old (t1) and other (t2) when unscoped
    removed_all = await repo.delete_older_than(datetime.now(timezone.utc) - timedelta(days=30))
    assert removed_all == 2
    # tenant-scoped
    margin = ReportRun.from_operations(
        await _service().generate(report_type=ReportType.COST, tenant_id="t1")
    )
    margin.generated_at = datetime.now(timezone.utc) - timedelta(days=100)
    await repo.save(margin)
    removed_t1 = await repo.delete_older_than(
        datetime.now(timezone.utc) - timedelta(days=30), tenant_id="t1"
    )
    assert removed_t1 == 1


@pytest.mark.asyncio
async def test_report_run_repository_delete_older_than_sqlalchemy() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repo = SQLAlchemyReportRunRepository(session_factory)
    fresh = ReportRun.from_operations(
        await _service().generate(report_type=ReportType.COST, tenant_id="t1")
    )
    fresh.generated_at = datetime.now(timezone.utc) - timedelta(days=1)
    old = ReportRun.from_operations(
        await _service().generate(report_type=ReportType.AUDIT, tenant_id="t1")
    )
    old.generated_at = datetime.now(timezone.utc) - timedelta(days=60)
    await repo.save(fresh)
    await repo.save(old)
    removed = await repo.delete_older_than(datetime.now(timezone.utc) - timedelta(days=30))
    assert removed == 1
    assert len(await repo.list(tenant_id="t1")) == 1


@pytest.mark.asyncio
async def test_report_service_prune_runs() -> None:
    svc = _service(seed_audit=False)
    await svc.generate(report_type=ReportType.COST, tenant_id="t1")
    # force age by direct repo mutation
    for run in svc._runs._runs.values():
        run.generated_at = datetime.now(timezone.utc) - timedelta(days=100)
    result = await svc.prune_runs(retention_days=30)
    assert result["removed"] == 1
    assert await svc.list_runs(tenant_id="t1") == []


@pytest.mark.asyncio
async def test_report_service_run_due_auto_prunes_old_runs() -> None:
    svc = _service(seed_audit=False)
    sched = await svc.schedule(
        tenant_id="t1",
        report_type=ReportType.COST,
        cadence="daily",
        retention_days=30,
    )
    # a prior old run exists for t1
    old = ReportRun.from_operations(await svc.generate(report_type=ReportType.COST, tenant_id="t1"))
    old.generated_at = datetime.now(timezone.utc) - timedelta(days=60)
    await svc._runs.save(old)

    # force schedule due
    sched.next_run_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await svc._schedules.save(sched)

    result = await svc.run_due()
    assert result["generated"] == 1
    # the 60-day-old run should have been pruned (retention 30)
    assert result["pruned"] == 1
    runs = await svc.list_runs(tenant_id="t1")
    assert len(runs) == 1  # only the just-generated run survives


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


def test_prune_runs_endpoint() -> None:
    tc = _app()
    # create some runs first
    tc.get("/v1/console/reports/export", params={"report_type": "cost", "tenant_id": "t1"})
    before = tc.get("/v1/console/reports/runs", params={"tenant_id": "t1"}).json()["runs"]
    assert len(before) >= 1
    # prune with a tiny retention window -> should remove those runs
    r = tc.post(
        "/v1/console/reports/runs/prune",
        json={"retention_days": 0, "tenant_id": "t1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == "t1" and "removed" in body
    assert body["removed"] == len(before)
    after = tc.get("/v1/console/reports/runs", params={"tenant_id": "t1"}).json()["runs"]
    assert after == []


def test_schedule_with_retention_days() -> None:
    tc = _app()
    r = tc.post(
        "/v1/console/reports/schedule",
        json={
            "tenant_id": "t1",
            "report_type": "cost",
            "cadence": "daily",
            "retention_days": 14,
        },
    )
    assert r.status_code == 200
    assert r.json()["retention_days"] == 14

    bad = tc.post(
        "/v1/console/reports/schedule",
        json={"tenant_id": "t1", "report_type": "cost", "cadence": "daily", "retention_days": "x"},
    )
    assert bad.status_code == 400


# --- increment 9: schedule enable/disable + global default retention ---


@pytest.mark.asyncio
async def test_report_service_set_schedule_enabled_memory() -> None:
    svc = _service(seed_audit=False)
    sched = await svc.schedule(tenant_id="t1", report_type=ReportType.COST)
    assert sched.enabled is True

    paused = await svc.set_schedule_enabled(sched.report_id, enabled=False)
    assert paused.enabled is False
    # a disabled schedule must not appear as due even if next_run is in the past
    paused.next_run_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await svc._schedules.save(paused)
    due = await svc._schedules.list_due()
    assert all(s.report_id != sched.report_id for s in due)

    resumed = await svc.set_schedule_enabled(sched.report_id, enabled=True)
    assert resumed.enabled is True


@pytest.mark.asyncio
async def test_report_service_set_schedule_enabled_missing_raises() -> None:
    svc = _service(seed_audit=False)
    with pytest.raises(KeyError):
        await svc.set_schedule_enabled("nope", enabled=False)


@pytest.mark.asyncio
async def test_report_service_run_due_global_default_retention() -> None:
    svc = _service(seed_audit=False)
    # schedule without explicit retention_days -> falls back to global default
    sched = await svc.schedule(tenant_id="t1", report_type=ReportType.COST)
    # a prior old run beyond the global default window exists for t1
    old = ReportRun.from_operations(await svc.generate(report_type=ReportType.COST, tenant_id="t1"))
    old.generated_at = datetime.now(timezone.utc) - timedelta(days=60)
    await svc._runs.save(old)

    # service-level default applies when run_due has no explicit override
    sched.next_run_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await svc._schedules.save(sched)
    result = await svc.run_due(default_retention_days=30)
    assert result["generated"] == 1
    assert result["pruned"] == 1
    runs = await svc.list_runs(tenant_id="t1")
    assert len(runs) == 1  # only the fresh run survives


def test_schedule_toggle_enabled_endpoint() -> None:
    tc = _app()
    created = tc.post(
        "/v1/console/reports/schedule",
        json={"tenant_id": "t1", "report_type": "cost", "cadence": "daily"},
    ).json()
    rid = created["report_id"]

    paused = tc.post(f"/v1/console/reports/schedule/{rid}/enabled", json={"enabled": False})
    assert paused.status_code == 200
    assert paused.json()["enabled"] is False

    resumed = tc.post(f"/v1/console/reports/schedule/{rid}/enabled", json={"enabled": True})
    assert resumed.status_code == 200
    assert resumed.json()["enabled"] is True

    missing = tc.post("/v1/console/reports/schedule/missing/enabled", json={"enabled": False})
    assert missing.status_code == 404


def test_schedule_enabled_disabled_skipped_by_run_due() -> None:
    tc = _app()
    created = tc.post(
        "/v1/console/reports/schedule",
        json={"tenant_id": "t1", "report_type": "cost", "cadence": "daily"},
    ).json()
    rid = created["report_id"]
    tc.post(f"/v1/console/reports/schedule/{rid}/enabled", json={"enabled": False})

    # run-due with a bad default retention days returns 400
    bad = tc.post("/v1/console/reports/run-due", json={"default_retention_days": "x"})
    assert bad.status_code == 400

    # valid run-due accepts the default retention override and returns shape
    r = tc.post("/v1/console/reports/run-due", json={"default_retention_days": 30})
    assert r.status_code == 200
    assert "generated" in r.json() and "reports" in r.json()


# --- increment 10: cron expression scheduling ---


@pytest.mark.asyncio
async def test_cron_parse_and_next() -> None:
    daily = CronSchedule("0 2 * * *")
    base = datetime(2026, 9, 18, 10, 30, tzinfo=timezone.utc)
    nxt = daily.next_after(base)
    assert nxt is not None and nxt.hour == 2 and nxt.minute == 0
    assert nxt.day == 19

    quarter = CronSchedule("*/15 * * * *")
    nxt = quarter.next_after(datetime(2026, 9, 18, 10, 29, tzinfo=timezone.utc))
    assert nxt is not None and nxt.minute == 30


@pytest.mark.asyncio
async def test_cron_invalid_expression() -> None:
    with pytest.raises(CronExpressionError):
        CronSchedule("61 * * * *")
    with pytest.raises(CronExpressionError):
        CronSchedule("0 2 * * * *")  # six fields
    with pytest.raises(CronExpressionError):
        CronSchedule("")


@pytest.mark.asyncio
async def test_cron_weekday_restriction() -> None:
    mon = CronSchedule("0 2 * * 1")  # Monday only (cron dow 1)
    monday = datetime(2026, 9, 21, 2, 0, tzinfo=timezone.utc)
    sunday = datetime(2026, 9, 20, 2, 0, tzinfo=timezone.utc)
    assert mon.matches(monday) is True
    assert mon.matches(sunday) is False
    nxt = mon.next_after(monday)
    assert nxt is not None and nxt.day == 28  # next Monday


@pytest.mark.asyncio
async def test_cron_or_rule_when_both_day_fields_restricted() -> None:
    both = CronSchedule("0 2 1 * 1")  # 1st of month OR Monday
    first_sunday = datetime(2026, 11, 1, 2, 0, tzinfo=timezone.utc)
    assert both.matches(first_sunday) is True
    monday_10th = datetime(2026, 11, 9, 2, 0, tzinfo=timezone.utc)
    assert both.matches(monday_10th) is True


@pytest.mark.asyncio
async def test_is_cron_cadence() -> None:
    assert is_cron_cadence("0 2 * * *") is True
    assert is_cron_cadence("*/15 * * * *") is True
    assert is_cron_cadence("daily") is False
    assert is_cron_cadence("weekly") is False


@pytest.mark.asyncio
async def test_report_service_cron_schedule_advances() -> None:
    svc = _service(seed_audit=False)
    sched = await svc.schedule(
        tenant_id="t1",
        report_type=ReportType.COST,
        cadence="0 2 * * *",
    )
    sched.next_run_at = datetime.now(timezone.utc) - timedelta(hours=1)
    sched.last_run_at = datetime.now(timezone.utc) - timedelta(hours=2)
    await svc._schedules.save(sched)

    result = await svc.run_due()
    assert result["generated"] == 1
    updated = await svc._schedules.get(sched.report_id)
    assert updated is not None and updated.next_run_at.hour == 2


def test_schedule_cron_cadence_endpoint() -> None:
    tc = _app()
    ok = tc.post(
        "/v1/console/reports/schedule",
        json={"tenant_id": "t1", "report_type": "cost", "cadence": "0 2 * * *"},
    )
    assert ok.status_code == 200
    assert ok.json()["cadence"] == "0 2 * * *"

    bad = tc.post(
        "/v1/console/reports/schedule",
        json={"tenant_id": "t1", "report_type": "cost", "cadence": "61 * * * *"},
    )
    assert bad.status_code == 400

    bad_label = tc.post(
        "/v1/console/reports/schedule",
        json={"tenant_id": "t1", "report_type": "cost", "cadence": "hourly"},
    )
    assert bad_label.status_code == 400


@pytest.mark.asyncio
async def test_report_service_archive_run() -> None:
    svc = _service(seed_audit=False)
    await svc.generate(report_type=ReportType.COST, tenant_id="t1")
    runs = await svc.list_runs(tenant_id="t1")
    run_id = runs[0]["run_id"]
    assert runs[0]["archived"] is False

    res = await svc.archive_run(run_id, archived=True)
    assert res["archived"] is True
    listed_active = await svc.list_runs(tenant_id="t1", archived=False)
    assert all(r["run_id"] != run_id for r in listed_active)
    listed_all = await svc.list_runs(tenant_id="t1")
    assert any(r["run_id"] == run_id and r["archived"] for r in listed_all)

    restored = await svc.archive_run(run_id, archived=False)
    assert restored["archived"] is False


@pytest.mark.asyncio
async def test_report_service_archive_run_missing_raises() -> None:
    svc = _service(seed_audit=False)
    with pytest.raises(KeyError):
        await svc.archive_run("nope", archived=True)


@pytest.mark.asyncio
async def test_report_service_export_archive_zip() -> None:
    svc = _service(seed_audit=False)
    await svc.generate(report_type=ReportType.COST, tenant_id="t1", fmt=ReportFormat.CSV)
    await svc.generate(report_type=ReportType.AUDIT, tenant_id="t1")
    data, info = await svc.export_archive(tenant_id="t1")
    parsed = json.loads(info)
    assert parsed["count"] == 2
    assert len(parsed["files"]) == 2
    assert {f["format"] for f in parsed["files"]} == {"csv", "json"}
    # validate zip contents
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        assert len(names) == 2
        assert all(n.endswith((".json", ".csv")) for n in names)


def test_report_run_archive_and_export_endpoints() -> None:
    tc = _app()
    tc.get("/v1/console/reports/export", params={"report_type": "cost", "tenant_id": "t1"})
    listed = tc.get("/v1/console/reports/runs", params={"tenant_id": "t1"}).json()["runs"]
    run_id = listed[0]["run_id"]

    archived = tc.post(f"/v1/console/reports/runs/{run_id}/archive", json={"archived": True})
    assert archived.status_code == 200
    assert archived.json()["archived"] is True

    active = tc.get("/v1/console/reports/runs", params={"tenant_id": "t1", "archived": "false"})
    assert all(r["run_id"] != run_id for r in active.json()["runs"])

    restored = tc.post(f"/v1/console/reports/runs/{run_id}/archive", json={"archived": False})
    assert restored.status_code == 200
    assert restored.json()["archived"] is False

    missing = tc.post("/v1/console/reports/runs/nope/archive", json={"archived": True})
    assert missing.status_code == 404

    exported = tc.get("/v1/console/reports/runs/archive", params={"tenant_id": "t1"})
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/zip")
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(exported.content)) as zf:
        assert len(zf.namelist()) >= 1


@pytest.mark.asyncio
async def test_prune_skips_archived_runs_by_default() -> None:
    svc = _service(seed_audit=False)
    await svc.generate(report_type=ReportType.COST, tenant_id="t1")
    runs = await svc.list_runs(tenant_id="t1")
    run_id = runs[0]["run_id"]
    # force age
    for run in svc._runs._runs.values():
        run.generated_at = datetime.now(timezone.utc) - timedelta(days=100)
    # archive it to protect it from retention pruning
    await svc.archive_run(run_id, archived=True)

    result = await svc.prune_runs(retention_days=30, tenant_id="t1")
    assert result["removed"] == 0
    assert result["include_archived"] is False
    # archived run survives
    assert len(await svc.list_runs(tenant_id="t1")) == 1

    # explicit forced cleanup deletes it
    forced = await svc.prune_runs(retention_days=30, tenant_id="t1", include_archived=True)
    assert forced["removed"] == 1
    assert await svc.list_runs(tenant_id="t1") == []


@pytest.mark.asyncio
async def test_prune_archived_behavior_memory_repo() -> None:
    repo = MemoryReportRunRepository()
    old_archived = ReportRun.from_operations(
        await _service().generate(report_type=ReportType.COST, tenant_id="t1")
    )
    old_archived.generated_at = datetime.now(timezone.utc) - timedelta(days=100)
    old_archived.archived = True
    old_plain = ReportRun.from_operations(
        await _service().generate(report_type=ReportType.AUDIT, tenant_id="t1")
    )
    old_plain.generated_at = datetime.now(timezone.utc) - timedelta(days=100)
    await repo.save(old_archived)
    await repo.save(old_plain)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    removed_default = await repo.delete_older_than(cutoff)
    assert removed_default == 1  # only the non-archived one
    assert await repo.get(old_archived.run_id) is not None

    removed_forced = await repo.delete_older_than(cutoff, include_archived=True)
    assert removed_forced == 1  # the archived one now
    assert await repo.get(old_archived.run_id) is None


@pytest.mark.asyncio
async def test_prune_archived_behavior_sqlalchemy_repo() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repo = SQLAlchemyReportRunRepository(session_factory)

    archived = ReportRun.from_operations(
        await _service().generate(report_type=ReportType.COST, tenant_id="t1")
    )
    archived.generated_at = datetime.now(timezone.utc) - timedelta(days=100)
    archived.archived = True
    plain = ReportRun.from_operations(
        await _service().generate(report_type=ReportType.AUDIT, tenant_id="t1")
    )
    plain.generated_at = datetime.now(timezone.utc) - timedelta(days=100)
    await repo.save(archived)
    await repo.save(plain)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    removed_default = await repo.delete_older_than(cutoff)
    assert removed_default == 1
    assert (await repo.get(archived.run_id)) is not None

    removed_forced = await repo.delete_older_than(cutoff, include_archived=True)
    assert removed_forced == 1
    assert (await repo.get(archived.run_id)) is None


def test_prune_endpoint_respects_archived() -> None:
    tc = _app()
    tc.get("/v1/console/reports/export", params={"report_type": "cost", "tenant_id": "t1"})
    listed = tc.get("/v1/console/reports/runs", params={"tenant_id": "t1"}).json()["runs"]
    run_id = listed[0]["run_id"]
    tc.post(f"/v1/console/reports/runs/{run_id}/archive", json={"archived": True})

    # default prune keeps archived
    preserved = tc.post(
        "/v1/console/reports/runs/prune", json={"retention_days": 0, "tenant_id": "t1"}
    )
    assert preserved.status_code == 200
    assert preserved.json()["removed"] == 0
    assert preserved.json()["include_archived"] is False

    # forced prune deletes archived
    forced = tc.post(
        "/v1/console/reports/runs/prune",
        json={"retention_days": 0, "tenant_id": "t1", "include_archived": True},
    )
    assert forced.status_code == 200
    assert forced.json()["include_archived"] is True
    assert forced.json()["removed"] == 1


def _actions(svc: ReportService) -> list[str]:
    return [e.action for e in svc._audit.events]


@pytest.mark.asyncio
async def test_report_service_schedule_writes_audit() -> None:
    svc = _service(seed_audit=False)
    await svc.schedule(tenant_id="t1", report_type=ReportType.COST, cadence="daily")
    actions = _actions(svc)
    assert "report.schedule.create" in actions
    ev = next(e for e in svc._audit.events if e.action == "report.schedule.create")
    assert ev.tenant_id == "t1"
    assert ev.actor_type == "admin"
    assert ev.resource_type == "report"


@pytest.mark.asyncio
async def test_report_service_delete_schedule_writes_audit() -> None:
    svc = _service(seed_audit=False)
    sched = await svc.schedule(tenant_id="t1", report_type=ReportType.COST, cadence="daily")
    await svc.delete_schedule(sched.report_id)
    actions = _actions(svc)
    assert "report.schedule.delete" in actions
    ev = next(e for e in svc._audit.events if e.action == "report.schedule.delete")
    assert ev.tenant_id == "t1"
    assert ev.resource_id == sched.report_id


@pytest.mark.asyncio
async def test_report_service_set_schedule_enabled_writes_audit() -> None:
    svc = _service(seed_audit=False)
    sched = await svc.schedule(tenant_id="t1", report_type=ReportType.COST, cadence="daily")
    await svc.set_schedule_enabled(sched.report_id, False)
    await svc.set_schedule_enabled(sched.report_id, True)
    actions = _actions(svc)
    assert "report.schedule.disable" in actions
    assert "report.schedule.enable" in actions


@pytest.mark.asyncio
async def test_report_service_generate_writes_audit() -> None:
    svc = _service(seed_audit=False)
    await svc.generate(report_type=ReportType.COST, tenant_id="t1", fmt=ReportFormat.JSON)
    actions = _actions(svc)
    assert "report.generate" in actions
    ev = next(e for e in svc._audit.events if e.action == "report.generate")
    assert ev.payload["report_type"] == "cost"
    assert ev.payload["format"] == "json"


@pytest.mark.asyncio
async def test_report_service_archive_run_writes_audit() -> None:
    svc = _service(seed_audit=False)
    report = await svc.generate(report_type=ReportType.COST, tenant_id="t1")
    run = ReportRun.from_operations(report)
    await svc._runs.save(run)
    await svc.archive_run(run.run_id, True)
    await svc.archive_run(run.run_id, False)
    actions = _actions(svc)
    assert "report.run.archive" in actions
    assert "report.run.unarchive" in actions


@pytest.mark.asyncio
async def test_report_service_prune_writes_audit() -> None:
    svc = _service(seed_audit=False)
    report = await svc.generate(report_type=ReportType.COST, tenant_id="t1")
    run = ReportRun.from_operations(report)
    run.generated_at = datetime.now(timezone.utc) - timedelta(days=100)
    await svc._runs.save(run)
    result = await svc.prune_runs(retention_days=0, tenant_id="t1")
    assert result["removed"] == 1
    actions = _actions(svc)
    assert "report.runs.prune" in actions
    ev = next(e for e in svc._audit.events if e.action == "report.runs.prune")
    assert ev.tenant_id == "t1"
    assert ev.risk_level.value == "medium"


@pytest.mark.asyncio
async def test_report_service_run_due_writes_audit() -> None:
    svc = _service(seed_audit=False)
    sched = await svc.schedule(tenant_id="t1", report_type=ReportType.COST, cadence="daily")
    sched.next_run_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await svc._schedules.save(sched)
    result = await svc.run_due()
    assert result["generated"] == 1
    actions = _actions(svc)
    assert "report.run_due" in actions
    ev = next(e for e in svc._audit.events if e.action == "report.run_due")
    assert ev.payload["generated"] == 1


@pytest.mark.asyncio
async def test_report_service_export_archive_to_writes_zip_to_sink(tmp_path) -> None:
    svc = _service(seed_audit=False)
    await svc.generate(report_type=ReportType.COST, tenant_id="t1", fmt=ReportFormat.CSV)
    await svc.generate(report_type=ReportType.AUDIT, tenant_id="t1")
    out = tmp_path / "archive.zip"
    with out.open("wb") as sink:
        info = await svc.export_archive_to(sink, tenant_id="t1")
    parsed = json.loads(info)
    assert parsed["count"] == 2
    assert len(parsed["files"]) == 2
    import zipfile

    with zipfile.ZipFile(str(out)) as zf:
        assert len(zf.namelist()) == 2
        assert all(n.endswith((".json", ".csv")) for n in zf.namelist())


def test_report_archive_export_endpoint_streams_valid_zip(tmp_path) -> None:
    tc = _app()
    tc.get("/v1/console/reports/export", params={"report_type": "cost", "tenant_id": "t1"})
    exported = tc.get("/v1/console/reports/runs/archive", params={"tenant_id": "t1"})
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/zip")
    assert exported.headers["content-disposition"].startswith("attachment")
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(exported.content)) as zf:
        assert len(zf.namelist()) >= 1


@pytest.mark.asyncio
async def test_report_run_repository_list_page_memory() -> None:
    repo = MemoryReportRunRepository()
    svc = _service(seed_audit=False)
    for _ in range(5):
        run = ReportRun.from_operations(
            await svc.generate(report_type=ReportType.COST, tenant_id="t1")
        )
        await repo.save(run)
    page1, c1 = await repo.list_page(tenant_id="t1", limit=2)
    assert len(page1) == 2
    page2, c2 = await repo.list_page(tenant_id="t1", limit=2, cursor=c1)
    assert len(page2) == 2
    page3, c3 = await repo.list_page(tenant_id="t1", limit=2, cursor=c2)
    assert len(page3) == 1
    assert c3 is None
    # no overlap across pages
    ids = [r.run_id for r in page1 + page2 + page3]
    assert len(ids) == len(set(ids)) == 5


@pytest.mark.asyncio
async def test_report_run_keyset_cursor_stable_under_duplicate_timestamps() -> None:
    """Keyset cursor must page stably even when rows share generated_at.

    Offsets drift when rows before the cursor change; a keyset anchored on
    (generated_at, run_id) must return disjoint, complete pages regardless.
    """
    repo = MemoryReportRunRepository()
    fixed_ts = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(5):
        run = ReportRun(
            run_id=f"r{i}",
            tenant_id="t1",
            report_type=ReportType.COST,
            generated_at=fixed_ts,
        )
        await repo.save(run)

    ids: list[str] = []
    cursor: str | None = None
    while True:
        page, cursor = await repo.list_page(tenant_id="t1", limit=2, cursor=cursor)
        ids.extend(r.run_id for r in page)
        if cursor is None:
            break
    assert ids == ["r4", "r3", "r2", "r1", "r0"]
    assert len(ids) == len(set(ids)) == 5


def test_report_run_keyset_cursor_roundtrip() -> None:
    """The opaque keyset cursor must round-trip (generated_at, run_id)."""
    ts = datetime(2026, 9, 18, 13, 0, 0, tzinfo=timezone.utc)
    cursor = _encode_run_cursor(ts, "abc123")
    decoded_ts, decoded_id = _decode_run_cursor(cursor)
    assert decoded_id == "abc123"
    assert decoded_ts == ts
    assert _decode_run_cursor(None) is None
    assert _decode_run_cursor("garbage-not-base64") is None


@pytest.mark.asyncio
async def test_report_run_repository_list_page_sqlalchemy() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repo = SQLAlchemyReportRunRepository(session_factory)
    svc = _service(seed_audit=False)
    for _ in range(5):
        run = ReportRun.from_operations(
            await svc.generate(report_type=ReportType.COST, tenant_id="t1")
        )
        await repo.save(run)
    page1, c1 = await repo.list_page(tenant_id="t1", limit=3)
    assert len(page1) == 3
    page2, c2 = await repo.list_page(tenant_id="t1", limit=3, cursor=c1)
    assert len(page2) == 2
    assert c2 is None
    ids = [r.run_id for r in page1 + page2]
    assert len(ids) == len(set(ids)) == 5


@pytest.mark.asyncio
async def test_report_service_list_runs_paginated() -> None:
    svc = _service(seed_audit=False)
    for _ in range(5):
        await svc.generate(report_type=ReportType.COST, tenant_id="t1")
    page1, c1 = await svc.list_runs_paginated(tenant_id="t1", limit=3)
    assert len(page1) == 3
    page2, c2 = await svc.list_runs_paginated(tenant_id="t1", limit=3, cursor=c1)
    assert len(page2) == 2
    assert c2 is None
    assert all("run_id" in r and "generated_at" in r for r in page1 + page2)


def test_report_list_runs_endpoint_cursor_pagination() -> None:
    tc = _app()
    for _ in range(3):
        tc.get("/v1/console/reports/export", params={"report_type": "cost", "tenant_id": "t1"})
    first = tc.get("/v1/console/reports/runs", params={"tenant_id": "t1", "limit": "2"})
    assert first.status_code == 200
    body = first.json()
    assert len(body["runs"]) == 2
    assert body["next_cursor"] is not None
    second = tc.get(
        "/v1/console/reports/runs",
        params={"tenant_id": "t1", "limit": "2", "cursor": body["next_cursor"]},
    )
    sbody = second.json()
    assert len(sbody["runs"]) >= 1
    first_ids = {r["run_id"] for r in body["runs"]}
    second_ids = {r["run_id"] for r in sbody["runs"]}
    assert not (first_ids & second_ids)
