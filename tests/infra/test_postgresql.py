"""测试PostgreSQL测试模块。"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.priority import PriorityLevel
from agentforge.platform.infrastructure.db.base import create_session_factory
from agentforge.platform.infrastructure.outbox_dispatcher import OutboxDispatcher
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore
from agentforge.platform.infrastructure.persistence import SQLAlchemyPersistence
from agentforge.platform.modules.support.domain.ticket import Ticket, TicketStatus
from agentforge.platform.modules.support.infrastructure.sqlalchemy_repository import (
    SQLAlchemyTicketRepository,
)
from tests.infra.conftest import DATABASE_URL, REPO_ROOT, RUN_INFRA, run_migration_round_trip

pytestmark = [
    pytest.mark.infra,
    pytest.mark.skipif(not RUN_INFRA, reason="set AGENTFORGE_RUN_INFRA_TESTS=1"),
]


def test_migration_upgrade_downgrade_upgrade() -> None:
    """验证迁移升级对应的测试场景。"""
    run_migration_round_trip()
    env = dict(os.environ)
    env["AGENTFORGE_DATABASE_URL"] = DATABASE_URL
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_module_schemas_and_unique_constraints_exist() -> None:
    """验证模块结构及约束存在对应的测试场景。"""
    session_factory = create_session_factory(DATABASE_URL)
    async with session_factory() as session:
        schemas = set(
            (
                await session.execute(
                    text(
                        "SELECT schema_name FROM information_schema.schemata "
                        "WHERE schema_name IN ('module_support', 'module_expense')"
                    )
                )
            ).scalars()
        )
        index_names = set(
            (
                await session.execute(
                    text("SELECT indexname FROM pg_indexes " "WHERE schemaname = 'module_expense'")
                )
            ).scalars()
        )
    assert schemas == {"module_support", "module_expense"}
    assert "uq_expense_invoice_gate_alerts_active_key" in index_names


@pytest.mark.asyncio
async def test_json_sla_query_and_tenant_isolation_on_postgresql() -> None:
    """验证JSONSLA查询及租户隔离时PostgreSQL对应的测试场景。"""
    base_factory = create_session_factory(DATABASE_URL)
    support_factory = SQLAlchemyPersistence(base_factory).session_factory_for("support")
    repository = SQLAlchemyTicketRepository(support_factory)
    now = datetime.now(timezone.utc)
    overdue_id = f"pg-overdue-{uuid4()}"
    healthy_id = f"pg-healthy-{uuid4()}"
    overdue = Ticket(
        ticket_id=overdue_id,
        tenant_id="tenant-pg-a",
        source="feishu",
        subject="overdue",
        status=TicketStatus.WAITING_REVIEW,
        priority=PriorityLevel.P2,
        assigned_team="support",
        idempotency_key=overdue_id,
        metadata={
            "queue": "support",
            "sla": {
                "due_at": (now - timedelta(minutes=10)).isoformat(),
                "status": "open",
            },
        },
    )
    healthy = Ticket(
        ticket_id=healthy_id,
        tenant_id="tenant-pg-a",
        source="feishu",
        subject="healthy",
        status=TicketStatus.WAITING_REVIEW,
        priority=PriorityLevel.P2,
        assigned_team="support",
        idempotency_key=healthy_id,
        metadata={
            "queue": "support",
            "sla": {
                "due_at": (now + timedelta(hours=2)).isoformat(),
                "status": "open",
            },
        },
    )
    await repository.save(overdue)
    await repository.save(healthy)

    overdue_rows, _ = await repository.list("tenant-pg-a", overdue=True, limit=100)
    forbidden_rows, _ = await repository.list("tenant-pg-b", limit=100)
    assert {ticket.ticket_id for ticket in overdue_rows} == {overdue_id}
    assert forbidden_rows == []


class FlakyPublisher:
    """按指定失败次数工作的不稳定事件发布器。"""

    def __init__(self, failures: int) -> None:
        """初始化不稳定发布器。

        Args:
            failures: 输入参数。
        """
        self.failures = failures
        self.published: list[str] = []

    async def publish(self, event: EventEnvelope) -> None:
        """发布不稳定发布器。

        Args:
            event: 待处理事件。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        if self.failures:
            self.failures -= 1
            raise RuntimeError("publisher unavailable")
        self.published.append(event.event_id)


@pytest.mark.asyncio
async def test_outbox_fault_injection_does_not_lose_event_or_repeat_handler() -> None:
    """验证Outbox会不事件或处理器对应的测试场景。"""
    session_factory = create_session_factory(DATABASE_URL)
    store = SQLAlchemyOutboxStore(session_factory, max_attempts=3)
    event_id = f"pg-outbox-{uuid4()}"
    event = EventEnvelope(
        event_id=event_id,
        event_type="support.ticket.created.v1",
        tenant_id="tenant-pg-outbox",
        task_id="task-1",
        trace_id="trace-1",
        producer="infra-test",
    )
    await store.enqueue(event)
    handler_calls = 0

    async def handler(_event: EventEnvelope) -> None:
        """处理测试场景中的异步请求。

        Args:
            _event: 事件。
        """
        nonlocal handler_calls
        handler_calls += 1

    publisher = FlakyPublisher(failures=1)
    dispatcher = OutboxDispatcher(
        store,
        publisher,
        event_handlers={"support.ticket.created.v1": handler},
    )
    assert await dispatcher.dispatch_once(limit=1000) == 0
    assert await dispatcher.dispatch_once(limit=1000) == 1
    detail = await store.get_event("tenant-pg-outbox", event_id)
    assert detail is not None
    assert detail["status"] == "published"
    assert handler_calls == 1
    assert publisher.published == [event_id]
