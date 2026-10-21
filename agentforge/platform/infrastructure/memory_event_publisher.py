"""记忆事件发布器模块。"""

from __future__ import annotations

from agentforge.platform.domain.events import EventEnvelope


class MemoryEventPublisher:
    """事件发布器相关组件。"""

    def __init__(self) -> None:
        """初始化 MemoryEventPublisher。"""
        self.events: list[EventEnvelope] = []

    async def publish(self, event: EventEnvelope) -> None:
        """发布事件发布器。

        Args:
            event: 待处理事件。
        """
        self.events.append(event)
