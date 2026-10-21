"""工单测试模块。

本测试模块验证 test_ticket 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：make_ticket、test_ticket_valid_transition、test_ticket_rejects_invalid_transition、test_idempo
    tent_repository_lookup。
"""

import pytest

from agentforge.platform.modules.support.domain.ticket import Ticket, TicketStatus
from agentforge.platform.modules.support.infrastructure.memory_repository import (
    MemoryTicketRepository,
)


def make_ticket() -> Ticket:
    """构造工单。

    Returns:
        工单结果。
    """
    return Ticket(
        ticket_id="ticket-1",
        tenant_id="tenant-1",
        source="feishu",
        idempotency_key="event-1",
    )


def test_ticket_valid_transition() -> None:
    """验证工单有效状态转换对应的测试场景。"""
    ticket = make_ticket()
    ticket.transition_to(TicketStatus.CLASSIFYING)
    ticket.transition_to(TicketStatus.WAITING_REVIEW)
    assert ticket.status == TicketStatus.WAITING_REVIEW
    assert ticket.version == 3


def test_ticket_rejects_invalid_transition() -> None:
    """验证工单拒绝无效状态转换对应的测试场景。"""
    ticket = make_ticket()
    with pytest.raises(ValueError):
        ticket.transition_to(TicketStatus.PUBLISHED)


@pytest.mark.asyncio
async def test_idempotent_repository_lookup() -> None:
    """验证幂等仓储对应的测试场景。"""
    repo = MemoryTicketRepository()
    ticket = make_ticket()
    await repo.save(ticket)
    found = await repo.get_by_idempotency_key("tenant-1", "event-1")
    assert found is not None
    assert found.ticket_id == "ticket-1"
