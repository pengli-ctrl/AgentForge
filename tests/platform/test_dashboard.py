from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.application.dashboard_service import DashboardService
from agentforge.platform.domain.cost import CostRecord
from agentforge.platform.domain.regression import RegressionRun, RegressionRunStatus
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.db.models import CostRecordRecord
from agentforge.platform.infrastructure.memory_cost_repository import MemoryCostRepository
from agentforge.platform.infrastructure.memory_regression_repository import (
    MemoryRegressionRepository,
)
from agentforge.platform.infrastructure.memory_tenant_quota_repository import (
    MemoryTenantQuotaRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_cost_repository import SQLAlchemyCostRepository
from agentforge.platform.runtime import build_memory_container


def _cost(
    tenant: str,
    model: str,
    amount: float,
    days_ago: int = 0,
) -> CostRecord:
    return CostRecord(
        tenant_id=tenant,
        task_id=f"task-{tenant}-{model}-{days_ago}",
        model_name=model,
        provider="litellm",
        input_tokens=100,
        output_tokens=50,
        amount=amount,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )


@pytest.mark.asyncio
async def test_memory_cost_daily_summary_groups_and_filters() -> None:
    repo = MemoryCostRepository()
    await repo.save(_cost("t1", "gpt", 1.0, days_ago=0))
    await repo.save(_cost("t1", "gpt", 2.0, days_ago=0))
    await repo.save(_cost("t1", "claude", 4.0, days_ago=1))
    await repo.save(_cost("t1", "old", 9.0, days_ago=400))  # 超出 days 窗口
    await repo.save(_cost("t2", "gpt", 99.0, days_ago=0))  # 别的租户

    daily = await repo.daily_summary("t1", days=30)
    assert len(daily) == 2  # 两天
    assert daily[0]["request_count"] == 1
    assert daily[0]["amount"] == 4.0  # days_ago=1 的那条
    assert daily[1]["request_count"] == 2
    assert daily[1]["amount"] == 3.0  # 1.0 + 2.0
    assert daily[0]["date"] < daily[1]["date"]


@pytest.mark.asyncio
async def test_dashboard_service_aggregates_all_sections() -> None:
    cost = MemoryCostRepository()
    quota = MemoryTenantQuotaRepository()
    regression = MemoryRegressionRepository()
    await cost.save(_cost("t1", "gpt", 2.0, days_ago=0))
    await cost.save(_cost("t1", "gpt", 3.0, days_ago=1))
    await cost.save(_cost("t1", "claude", 7.0, days_ago=1))
    await regression.save_run(
        RegressionRun(
            run_id="r1",
            tenant_id="t1",
            candidate_id="c1",
            status=RegressionRunStatus.PASSED,
            recall_at_k=0.9,
            citation_accuracy=0.8,
            classification_accuracy=0.85,
            priority_accuracy=0.7,
            structured_output_rate=1.0,
            high_risk_miss_rate=0.0,
            verdict="pass",
        )
    )

    service = DashboardService(cost, quota, regression)

    trend = await service.cost_trend("t1", days=30)
    assert trend["total_requests"] == 3
    assert len(trend["daily"]) == 2

    dist = await service.model_distribution("t1")
    assert len(dist["models"]) == 2
    # 按 cost 降序：claude(5) 在前
    assert dist["models"][0]["model_name"] == "claude"
    assert dist["models"][0]["share"] == pytest.approx(7.0 / 12.0, rel=1e-3)
    assert dist["total_amount"] == 12.0

    snapshot = await service.quota_snapshot("t1")
    assert snapshot["configured"] is False
    assert snapshot["used"] == 12.0

    q = await service.quality_metrics("t1")
    assert q["configured"] is True
    assert q["run_count"] == 1
    assert q["recent"]["run_id"] == "r1"
    assert q["averages"]["recall_at_k"] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_sqlalchemy_cost_daily_summary() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    repo = SQLAlchemyCostRepository(async_sessionmaker(engine, expire_on_commit=False))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: _bulk_insert_costs(sync_conn))
    daily = await repo.daily_summary("t1", days=30)
    assert len(daily) == 2
    assert daily[0]["amount"] == 4.0
    assert daily[1]["amount"] == 3.0
    await engine.dispose()


def _bulk_insert_costs(sync_conn) -> None:
    # 复用 ORM Core 直接插两条不同日期，避免再次起 async session
    from sqlalchemy import insert

    now = datetime.now(timezone.utc)
    sync_conn.execute(
        insert(CostRecordRecord),
        [
            {
                "tenant_id": "t1",
                "task_id": "a",
                "model_name": "gpt",
                "provider": "litellm",
                "input_tokens": 100,
                "output_tokens": 50,
                "amount": 4.0,
                "created_at": now - timedelta(days=1),
            },
            {
                "tenant_id": "t1",
                "task_id": "b",
                "model_name": "gpt",
                "provider": "litellm",
                "input_tokens": 100,
                "output_tokens": 50,
                "amount": 3.0,
                "created_at": now,
            },
        ],
    )


def test_dashboard_endpoints_memory() -> None:
    container = build_memory_container()
    client = TestClient(create_platform_app(container))

    async def seed():
        await container.cost_repository.save(_cost("t1", "gpt", 2.0, days_ago=0))
        await container.cost_repository.save(_cost("t1", "gpt", 3.0, days_ago=1))
        await container.cost_repository.save(_cost("t1", "claude", 7.0, days_ago=1))
        await container.regression_repository.save_run(
            RegressionRun(
                run_id="r1",
                tenant_id="t1",
                candidate_id="c1",
                status=RegressionRunStatus.PASSED,
                recall_at_k=0.9,
                verdict="pass",
            )
        )

    import asyncio

    asyncio.run(seed())

    dash = client.get("/v1/console/dashboard", params={"tenant_id": "t1"}).json()
    assert dash["cost_trend"]["total_requests"] == 3
    assert dash["model_distribution"]["total_amount"] == 12.0
    assert dash["quality"]["configured"] is True

    trend = client.get("/v1/console/cost-trend", params={"tenant_id": "t1", "days": 30}).json()
    assert len(trend["daily"]) == 2

    dist = client.get("/v1/console/model-distribution", params={"tenant_id": "t1"}).json()
    assert dist["models"][0]["model_name"] == "claude"

    q = client.get("/v1/console/quality", params={"tenant_id": "t1"}).json()
    assert q["recent"]["run_id"] == "r1"
