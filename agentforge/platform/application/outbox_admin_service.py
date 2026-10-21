"""Outbox管理服务模块。"""

from __future__ import annotations

from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore


class OutboxAdminService:
    """Outboxadmin应用服务，编排领域用例及其副作用。"""

    def __init__(self, store: SQLAlchemyOutboxStore) -> None:
        """初始化 OutboxAdminService。

        Args:
            store: 状态存储实例。
        """
        self._store = store

    async def list_failed(self, limit: int = 100) -> list[dict]:
        """查询失败。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        return await self._store.list_failed(limit=limit)

    async def replay(self, event_id: str) -> bool:
        """重放Outboxadmin。

        Args:
            event_id: 事件 ID。

        Returns:
            操作是否成功。
        """
        return await self._store.replay(event_id)

    async def replay_all(self, limit: int = 100) -> int:
        """重放全部。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            整数结果。
        """
        failed = await self._store.list_failed(limit=limit)
        replayed = 0
        for event in failed:
            if await self._store.replay(event["event_id"]):
                replayed += 1
        return replayed
