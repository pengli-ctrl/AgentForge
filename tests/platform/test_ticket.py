"""AgentForge 平台测试层：test_ticket。

本测试模块验证 test_ticket 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：make_ticket、test_ticket_valid_transition、test_ticket_rejects_invalid_transition、test_idempotent_repository_lookup。
"""

import pytest

from agentforge.platform.domain.ticket import Ticket, TicketStatus
from agentforge.platform.infrastructure.memory_ticket_repository import MemoryTicketRepository


def make_ticket() -> Ticket:
    """执行 make_ticket 对应的逻辑，并返回处理结果。

    Returns:
        Ticket，函数执行后的结果。
    """
    return Ticket(
        ticket_id="ticket-1",
        tenant_id="tenant-1",
        source="feishu",
        idempotency_key="event-1",
    )


def test_ticket_valid_transition() -> None:
    """验证 ticket_valid_transition 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    ticket = make_ticket()
    ticket.transition_to(TicketStatus.CLASSIFYING)
    ticket.transition_to(TicketStatus.WAITING_REVIEW)
    assert ticket.status == TicketStatus.WAITING_REVIEW
    assert ticket.version == 3


def test_ticket_rejects_invalid_transition() -> None:
    """验证 ticket_rejects_invalid_transition 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    ticket = make_ticket()
    with pytest.raises(ValueError):
        ticket.transition_to(TicketStatus.PUBLISHED)


@pytest.mark.asyncio
async def test_idempotent_repository_lookup() -> None:
    """验证 idempotent_repository_lookup 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    repo = MemoryTicketRepository()
    ticket = make_ticket()
    await repo.save(ticket)
    found = await repo.get_by_idempotency_key("tenant-1", "event-1")
    assert found is not None
    assert found.ticket_id == "ticket-1"
