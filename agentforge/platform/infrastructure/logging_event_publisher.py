"""AgentForge 平台基础设施层：logging_event_publisher。

本模块负责 logging_event_publisher 相关的平台能力，是 平台基础设施层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：LoggingEventPublisher。
"""

from __future__ import annotations

import logging

from agentforge.platform.domain.events import EventEnvelope

logger = logging.getLogger(__name__)


class LoggingEventPublisher:
    """LoggingEventPublisher。

    LoggingEventPublisher 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 publish()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def publish(self, event: EventEnvelope) -> None:
        """执行 publish 对应的核心操作，并保持调用契约稳定。

        Args:
            event: EventEnvelope，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        logger.info(
            "Publishing domain event event_type=%s tenant_id=%s task_id=%s",
            event.event_type,
            event.tenant_id,
            event.task_id,
        )
