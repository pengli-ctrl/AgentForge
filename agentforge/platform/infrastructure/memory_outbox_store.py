from __future__ import annotations

from dataclasses import dataclass

from agentforge.platform.domain.events import EventEnvelope


@dataclass
class _OutboxEntry:
    event: EventEnvelope
    status: str
    attempts: int = 0
    last_error: str | None = None
    published_at: str | None = None


class MemoryOutboxStore:
    """In-memory outbox store providing the same admin surface as SQLAlchemyOutboxStore.

    Suitable for local/demo runs without a database.
    """

    def __init__(self) -> None:
        self._entries: dict[str, _OutboxEntry] = {}

    async def enqueue(self, event: EventEnvelope) -> None:
        if event.event_id in self._entries:
            return
        self._entries[event.event_id] = _OutboxEntry(event=event, status="pending")

    async def fetch_pending(self, limit: int = 100) -> list[EventEnvelope]:
        pending = [e.event for e in self._entries.values() if e.status == "pending"][:limit]
        return pending

    async def mark_published(self, event_id: str) -> None:
        entry = self._entries.get(event_id)
        if entry is None:
            return
        entry.status = "published"
        entry.attempts += 0
        entry.published_at = entry.event.occurred_at.isoformat()

    async def mark_failed(self, event_id: str, error: str) -> None:
        entry = self._entries.get(event_id)
        if entry is None:
            return
        entry.attempts += 1
        entry.last_error = error[:2000]

    async def list_failed(self, limit: int = 100) -> list[dict]:
        failed = [e for e in self._entries.values() if e.status == "failed"]
        return [self._summary(e) for e in failed[:limit]]

    async def list_events(
        self,
        tenant_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[dict], str | None]:
        entries = list(self._entries.values())
        entries.sort(key=lambda e: e.event.occurred_at)
        if tenant_id is not None:
            entries = [e for e in entries if e.event.tenant_id == tenant_id]
        if status is not None:
            entries = [e for e in entries if e.status == status]
        start = int(cursor) if (cursor is not None and cursor.isdigit()) else 0
        bucket = entries[start : start + limit]
        next_cursor = str(start + len(bucket)) if start + len(bucket) < len(entries) else None
        return [self._summary(e) for e in bucket], next_cursor

    async def get_event(self, tenant_id: str | None, event_id: str) -> dict | None:
        entry = self._entries.get(event_id)
        if entry is None:
            return None
        if tenant_id is not None and entry.event.tenant_id != tenant_id:
            return None
        return {
            "event_id": entry.event.event_id,
            "tenant_id": entry.event.tenant_id,
            "event_type": entry.event.event_type,
            "status": entry.status,
            "attempts": entry.attempts,
            "last_error": entry.last_error,
            "payload": entry.event.payload,
            "created_at": entry.event.occurred_at.isoformat(),
            "published_at": entry.published_at,
        }

    async def count_events(self, tenant_id: str | None = None) -> dict[str, int]:
        counts = {"pending": 0, "published": 0, "failed": 0, "discarded": 0}
        for entry in self._entries.values():
            if tenant_id is not None and entry.event.tenant_id != tenant_id:
                continue
            if entry.status in counts:
                counts[entry.status] += 1
        return counts

    async def discard(self, tenant_id: str | None, event_id: str) -> bool:
        entry = self._entries.get(event_id)
        if entry is None:
            return False
        if tenant_id is not None and entry.event.tenant_id != tenant_id:
            return False
        entry.status = "discarded"
        if not entry.last_error:
            entry.last_error = "discarded by operator"
        return True

    async def replay(self, event_id: str) -> bool:
        entry = self._entries.get(event_id)
        if entry is None:
            return False
        entry.status = "pending"
        entry.attempts = 0
        entry.last_error = None
        return True

    @staticmethod
    def _summary(entry: _OutboxEntry) -> dict:
        return {
            "event_id": entry.event.event_id,
            "tenant_id": entry.event.tenant_id,
            "event_type": entry.event.event_type,
            "status": entry.status,
            "attempts": entry.attempts,
            "last_error": entry.last_error,
            "created_at": entry.event.occurred_at.isoformat(),
            "published_at": entry.published_at,
        }
