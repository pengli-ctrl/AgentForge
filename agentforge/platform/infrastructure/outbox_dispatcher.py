from __future__ import annotations

from agentforge.platform.application.ports import EventPublisher
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore


class OutboxDispatcher:
    def __init__(self, store: SQLAlchemyOutboxStore, publisher: EventPublisher) -> None:
        self._store = store
        self._publisher = publisher

    async def dispatch_once(self, limit: int = 100) -> int:
        events = await self._store.fetch_pending(limit=limit)
        published = 0
        for event in events:
            try:
                await self._publisher.publish(event)
                await self._store.mark_published(event.event_id)
                published += 1
            except Exception as exc:
                await self._store.mark_failed(event.event_id, str(exc))
        return published
