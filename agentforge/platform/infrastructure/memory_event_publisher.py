"""AgentForge 平台基础设施层：memory_event_publisher。

本模块负责 memory_event_publisher 相关的平台能力，是 平台基础设施层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：MemoryEventPublisher。
"""

from __future__ import annotations

from agentforge.platform.domain.events import EventEnvelope


class MemoryEventPublisher:
    """MemoryEventPublisher。

    MemoryEventPublisher 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 publish()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self.events: list[EventEnvelope] = []

    async def publish(self, event: EventEnvelope) -> None:
        """执行 publish 对应的核心操作，并保持调用契约稳定。

        Args:
            event: EventEnvelope，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.events.append(event)
