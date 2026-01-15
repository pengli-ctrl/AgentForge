"""AgentForge 平台测试层：test_outbox_api。

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

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.outbox_dispatcher import OutboxDispatcher
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore
from agentforge.platform.runtime import build_sqlalchemy_container


class FailingPublisher:
    """FailingPublisher。

    FailingPublisher 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 publish()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def publish(self, event):
        """执行 publish 对应的核心操作，并保持调用契约稳定。

        Args:
            event: Any，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        raise RuntimeError("kafka unavailable")


def test_outbox_admin_list_and_replay() -> None:
    """验证 outbox_admin_list_and_replay 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    import asyncio

    async def setup():
        """执行 setup 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
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
        await container.ticket_service.create_from_event(
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
        return engine, container

    engine, container = asyncio.run(setup())
    client = TestClient(create_platform_app(container))
    failed = client.get("/v1/outbox/failed").json()["events"]
    assert len(failed) == 1
    response = client.post(f"/v1/outbox/{failed[0]['event_id']}/replay")
    assert response.status_code == 200
    assert response.json()["replayed"] is True
    asyncio.run(engine.dispose())
