from __future__ import annotations

from agentforge.platform.domain.audit import AuditEvent


class MemoryAuditRepository:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def save(self, event: AuditEvent) -> None:
        self.events.append(event)

    async def list_events(
        self,
        tenant_id: str,
        limit: int = 100,
        resource_id: str | None = None,
    ) -> list[AuditEvent]:
        events = [
            event
            for event in self.events
            if event.tenant_id == tenant_id
            and (resource_id is None or event.resource_id == resource_id)
        ]
        return sorted(events, key=lambda event: event.occurred_at, reverse=True)[:limit]

    async def query_events(
        self,
        tenant_id: str | None = None,
        action: str | None = None,
        actor_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[AuditEvent], str | None]:
        events = [
            event
            for event in self.events
            if (tenant_id is None or event.tenant_id == tenant_id)
            and (action is None or event.action == action)
            and (actor_id is None or event.actor_id == actor_id)
            and (resource_id is None or event.resource_id == resource_id)
            and (resource_type is None or event.resource_type == resource_type)
        ]
        events.sort(key=lambda event: event.occurred_at, reverse=True)
        start = int(cursor) if (cursor is not None and cursor.isdigit()) else 0
        bucket = events[start : start + limit]
        next_cursor = str(start + len(bucket)) if start + len(bucket) < len(events) else None
        return bucket, next_cursor
