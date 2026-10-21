"""记忆仓储模块。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.modules.support.domain.ticket import Ticket, TicketStatus


class MemoryTicketRepository:
    """工单仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryTicketRepository。"""
        self._by_id: dict[tuple[str, str], Ticket] = {}
        self._by_idempotency: dict[tuple[str, str], str] = {}
        self.outbox: list[EventEnvelope] = []

    async def get(self, tenant_id: str, ticket_id: str) -> Ticket | None:
        """读取工单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            ticket_id: 工单 ID。

        Returns:
            工单无结果。
        """
        return self._by_id.get((tenant_id, ticket_id))

    async def save(
        self,
        ticket: Ticket,
        events: list[EventEnvelope] | None = None,
    ) -> Ticket:
        """保存工单。

        Args:
            ticket: 客服工单对象。
            events: 事件。

        Returns:
            工单结果。
        """
        self._by_id[(ticket.tenant_id, ticket.ticket_id)] = ticket
        self._by_idempotency[(ticket.tenant_id, ticket.idempotency_key)] = ticket.ticket_id
        if events:
            self.outbox.extend(events)
        return ticket

    async def get_by_idempotency_key(self, tenant_id: str, idempotency_key: str) -> Ticket | None:
        """获取由键。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            idempotency_key: 幂等键，用于避免重复处理。

        Returns:
            工单无结果。
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
        assigned_team: str | None = None,
        assignee_id: str | None = None,
        queue: str | None = None,
        overdue: bool = False,
        due_before: str | None = None,
    ) -> tuple[list[Ticket], str | None]:
        """查询工单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            status: 目标状态。
            limit: 返回记录的最大数量。
            cursor: 分页游标。
            assigned_team: 输入参数。
            assignee_id: 处理人 ID。
            queue: 队列。
            overdue: 逾期。
            due_before: 到期之前。

        Returns:
            结果元组。
        """
        tickets = [
            t
            for (t_tenant, _t_id), t in self._by_id.items()
            if (
                t_tenant == tenant_id
                and (status is None or t.status == status)
                and (assigned_team is None or t.assigned_team == assigned_team)
                and (assignee_id is None or t.assignee_id == assignee_id)
                and (
                    queue is None or str(t.metadata.get("queue") or t.assigned_team or "") == queue
                )
                and _matches_sla_filters(t, overdue=overdue, due_before=due_before)
            )
        ]
        tickets.sort(key=lambda t: t.created_at)
        start = int(cursor) if (cursor is not None and cursor.isdigit()) else 0
        bucket = tickets[start : start + limit]
        next_cursor = str(start + len(bucket)) if start + len(bucket) < len(tickets) else None
        return bucket, next_cursor

    async def list_all(self, limit: int = 10_000) -> Sequence[Ticket]:
        """查询全部。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        tickets = list(self._by_id.values())
        tickets.sort(key=lambda t: (t.created_at, t.ticket_id), reverse=True)
        return tickets[:limit]


def _matches_sla_filters(ticket: Ticket, *, overdue: bool, due_before: str | None) -> bool:
    """判断匹配结果SLA筛选条件是否成立。

    Args:
        ticket: 客服工单对象。
        overdue: 逾期。
        due_before: 到期之前。

    Returns:
        操作是否成功。
    """
    if not overdue and due_before is None:
        return True
    if ticket.status in {TicketStatus.PUBLISHED, TicketStatus.CANCELLED}:
        return False
    sla = ticket.metadata.get("sla")
    if not isinstance(sla, dict) or not isinstance(sla.get("due_at"), str):
        return False
    try:
        due_at = datetime.fromisoformat(str(sla["due_at"]))
    except ValueError:
        return False
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if overdue and due_at >= now:
        return False
    if due_before is not None:
        try:
            threshold = datetime.fromisoformat(due_before)
        except ValueError:
            return False
        if threshold.tzinfo is None:
            threshold = threshold.replace(tzinfo=timezone.utc)
        if due_at > threshold:
            return False
    return True
