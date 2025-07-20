from __future__ import annotations

import logging

from agentforge.platform.domain.events import EventEnvelope

logger = logging.getLogger(__name__)


class LoggingEventPublisher:
    async def publish(self, event: EventEnvelope) -> None:
        logger.info(
            "Publishing domain event event_type=%s tenant_id=%s task_id=%s",
            event.event_type,
            event.tenant_id,
            event.task_id,
        )
