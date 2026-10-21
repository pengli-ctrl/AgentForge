"""OutboxAPI测试模块。

本测试模块验证 test_outbox_api 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：FailingPublisher。
- 主要函数：test_outbox_admin_list_and_replay。
"""

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.outbox_dispatcher import OutboxDispatcher
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore
from agentforge.platform.runtime import build_sqlalchemy_container
from tests.platform.support_fixtures import configure_sqlalchemy_support, create_app_with_support


class FailingPublisher:
    """失败发布器相关组件。"""

    async def publish(self, event):
        """发布失败发布器。

        Args:
            event: 待处理事件。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        raise RuntimeError("kafka unavailable")


def test_outbox_admin_list_and_replay() -> None:
    """验证Outbox管理查询及对应的测试场景。"""
    import asyncio

    async def setup():
        """装配测试环境。

        Returns:
            处理结果。
        """
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
                "message_id": "admin-msg-1",
                "text": "How do I use this product?",
            }
        )
        store = SQLAlchemyOutboxStore(session_factory, max_attempts=1)
        dispatcher = OutboxDispatcher(store, FailingPublisher())
        await dispatcher.dispatch_once()
        return engine, container, support

    engine, container, support = asyncio.run(setup())
    client = TestClient(create_app_with_support(container, support))
    failed = client.get("/v1/outbox/failed").json()["events"]
    assert len(failed) == 1
    response = client.post(f"/v1/outbox/{failed[0]['event_id']}/replay")
    assert response.status_code == 200
    assert response.json()["replayed"] is True
    asyncio.run(engine.dispose())
