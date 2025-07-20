from __future__ import annotations

from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore


class OutboxAdminService:
    def __init__(self, store: SQLAlchemyOutboxStore) -> None:
        self._store = store

    async def list_failed(self, limit: int = 100) -> list[dict]:
        return await self._store.list_failed(limit=limit)

    async def replay(self, event_id: str) -> bool:
        return await self._store.replay(event_id)

    async def replay_all(self, limit: int = 100) -> int:
        failed = await self._store.list_failed(limit=limit)
        replayed = 0
        for event in failed:
            if await self._store.replay(event["event_id"]):
                replayed += 1
        return replayed
