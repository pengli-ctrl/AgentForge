"""测试报告清理边界测试模块。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.domain.reporting import ReportFormat, ReportRun, ReportType
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.memory_report_run_repository import (
    MemoryReportRunRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_report_run_repository import (
    SQLAlchemyReportRunRepository,
)


def _run() -> ReportRun:
    """在并行调度并发限制下执行一个 DAG 节点。

    Returns:
        报告运行结果。
    """
    return ReportRun(
        run_id="run-boundary",
        tenant_id="tenant-boundary",
        report_type=ReportType.COST,
        format=ReportFormat.JSON,
        generated_at=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_memory_prune_deletes_run_at_exact_cutoff() -> None:
    """验证记忆清理删除运行于精确截止时间对应的测试场景。"""
    repository = MemoryReportRunRepository()
    run = _run()
    await repository.save(run)

    removed = await repository.delete_older_than(run.generated_at, tenant_id=run.tenant_id)

    assert removed == 1
    assert await repository.get(run.run_id) is None


@pytest.mark.asyncio
async def test_sqlalchemy_prune_deletes_run_at_exact_cutoff() -> None:
    """验证SQLAlchemy清理删除运行于精确截止时间对应的测试场景。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repository = SQLAlchemyReportRunRepository(async_sessionmaker(engine, expire_on_commit=False))
    run = _run()
    await repository.save(run)

    removed = await repository.delete_older_than(run.generated_at, tenant_id=run.tenant_id)

    assert removed == 1
    assert await repository.get(run.run_id) is None
    await engine.dispose()
