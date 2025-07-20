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
