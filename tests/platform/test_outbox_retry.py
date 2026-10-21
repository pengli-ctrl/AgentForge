"""Outbox重试测试模块。

本测试模块验证 test_outbox_retry 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：FailingPublisher。
- 主要函数：test_outbox_moves_to_failed_and_can_be_replayed。
"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.outbox_dispatcher import OutboxDispatcher
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore
from agentforge.platform.runtime import build_sqlalchemy_container
from tests.platform.support_fixtures import configure_sqlalchemy_support


class FailingPublisher:
    """失败发布器相关组件。"""

    async def publish(self, event):
        """发布失败发布器。

        Args:
            event: 待处理事件。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        raise RuntimeError("broker unavailable")


@pytest.mark.asyncio
async def test_outbox_moves_to_failed_and_can_be_replayed() -> None:
    """验证Outbox移动到失败及可以为对应的测试场景。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    container = build_sqlalchemy_container(session_factory)
    support = configure_sqlalchemy_support(container, session_factory)
    await support.ticket_service.create_from_event(
        {
            "tenant_id": "tenant-1",
            "source": "feishu",
            "message_id": "retry-msg-1",
            "text": "How do I use this product?",
        }
    )
    store = SQLAlchemyOutboxStore(session_factory, max_attempts=2)
    dispatcher = OutboxDispatcher(store, FailingPublisher())
    await dispatcher.dispatch_once()
    await dispatcher.dispatch_once()
    failed = await store.list_failed()
    assert len(failed) == 1
    assert failed[0]["attempts"] == 2
    assert await store.replay(failed[0]["event_id"]) is True
    assert len(await store.fetch_pending()) == 1
    await engine.dispose()
