"""AgentForge 平台基础设施层：memory_ticket_repository。

本模块提供 memory_ticket_repository 的内存实现，用于单元测试、本地开发和离线验证。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：MemoryTicketRepository。
"""

from __future__ import annotations

from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.ticket import Ticket


class MemoryTicketRepository:
    """MemoryTicketRepository。

    MemoryTicketRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 get()。
    - 方法 save()。
    - 方法 get_by_idempotency_key()。
    - 方法 list()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._by_id: dict[tuple[str, str], Ticket] = {}
        self._by_idempotency: dict[tuple[str, str], str] = {}
        self.outbox: list[EventEnvelope] = []

    async def get(self, tenant_id: str, ticket_id: str) -> Ticket | None:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            ticket_id: str，调用方传入的 ticket_id 参数。

        Returns:
            Ticket | None，函数执行后的结果。
        """
        return self._by_id.get((tenant_id, ticket_id))

    async def save(
        self,
        ticket: Ticket,
        events: list[EventEnvelope] | None = None,
    ) -> Ticket:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            ticket: Ticket，调用方传入的 ticket 参数。
            events: list[EventEnvelope] | None，调用方传入的 events 参数。

        Returns:
            Ticket，函数执行后的结果。
        """
        self._by_id[(ticket.tenant_id, ticket.ticket_id)] = ticket
        self._by_idempotency[(ticket.tenant_id, ticket.idempotency_key)] = ticket.ticket_id
        if events:
            self.outbox.extend(events)
        return ticket

    async def get_by_idempotency_key(self, tenant_id: str, idempotency_key: str) -> Ticket | None:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            idempotency_key: str，调用方传入的 idempotency_key 参数。

        Returns:
            Ticket | None，函数执行后的结果。
        """
        ticket_id = self._by_idempotency.get((tenant_id, idempotency_key))
        if ticket_id is None:
            return None
        return self._by_id.get((tenant_id, ticket_id))

    async def list(
        self,
        tenant_id: str,
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[Ticket], str | None]:
        """执行 list 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            status: str | None，调用方传入的 status 参数。
            limit: int，调用方传入的 limit 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            tuple[list[Ticket], str | None]，函数执行后的结果。
        """
        tickets = [
            t
            for (t_tenant, _t_id), t in self._by_id.items()
            if t_tenant == tenant_id and (status is None or t.status == status)
        ]
        tickets.sort(key=lambda t: t.created_at)
        start = int(cursor) if (cursor is not None and cursor.isdigit()) else 0
        bucket = tickets[start : start + limit]
        next_cursor = str(start + len(bucket)) if start + len(bucket) < len(tickets) else None
        return bucket, next_cursor
