from __future__ import annotations

from agentforge.platform.domain.events import EventEnvelope


class MemoryEventPublisher:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def publish(self, event: EventEnvelope) -> None:
        self.events.append(event)
