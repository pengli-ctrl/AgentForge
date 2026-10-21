"""事件发布器模块。"""

from __future__ import annotations

import logging

from agentforge.platform.domain.events import EventEnvelope

logger = logging.getLogger(__name__)


class LoggingEventPublisher:
    """事件发布器相关组件。"""

    async def publish(self, event: EventEnvelope) -> None:
        """发布事件发布器。

        Args:
            event: 待处理事件。
        """
        logger.info(
            "Publishing domain event event_type=%s tenant_id=%s task_id=%s",
            event.event_type,
            event.tenant_id,
            event.task_id,
        )
