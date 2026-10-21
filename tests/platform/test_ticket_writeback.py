"""工单写回测试模块。

本测试模块验证 test_ticket_writeback 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：_FakeAuditRepo。
-
主要函数：test_writeback_success_and_audit、test_writeback_no_connector_raises、test_writeback_failure_
    raises_and_audits、test_writeback_uses_resolver。
"""

import pytest

from agentforge.platform.application.connector_registry import ConnectorRegistry
from agentforge.platform.application.openapi_adapter import OpenAPIAdapter
from agentforge.platform.domain.connector import ConnectorKind, ConnectorRiskLevel, ConnectorSpec
from agentforge.platform.modules.support.application.writeback import TicketWritebackService
from agentforge.platform.modules.support.domain.ticket import (
    RiskLevel,
    Ticket,
    TicketPriority,
    TicketStatus,
)


def _ticket() -> Ticket:
    """处理工单。

    Returns:
        工单结果。
    """
    return Ticket(
        ticket_id="ticket-wb-1",
        tenant_id="t1",
        customer_id="cust-1",
        conversation_id="conv-1",
        source="feishu",
        subject="Refund inquiry",
        status=TicketStatus.PUBLISHED,
        priority=TicketPriority.P1,
        intent="refund",
        risk_level=RiskLevel.LOW,
        idempotency_key="ik-ticket-wb-1",
        metadata={"reply": {"text": "We have approved your refund."}},
    )


async def _registry_with(
    connector_id: str, tenant_id: str, error: bool = False
) -> ConnectorRegistry:
    """处理注册表使用。

    Args:
        connector_id: 连接器 ID。
        tenant_id: 租户 ID，用于数据隔离。
        error: 错误。

    Returns:
        连接器注册表结果。
    """

    async def _request(method, url, **kw):  # noqa: ANN001, ANN202
        """处理请求。

        Args:
            method: HTTP 或业务方法名。
            url: 目标 URL。
            kw: 输入参数。

        Returns:
            处理结果。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        if error:
            raise RuntimeError("boom")
        return {"refunded": True}

    adapter = OpenAPIAdapter(
        "https://crm.test",
        request_fn=_request,
    )
    spec = ConnectorSpec(
        connector_id=connector_id,
        tenant_id=tenant_id,
        name="openapi",
        kind=ConnectorKind.OPENAPI,
        endpoint="https://crm.test",
        risk_level=ConnectorRiskLevel.MEDIUM,
        allowed_actions=["writeback", "ticket.writeback"],
    )
    registry = ConnectorRegistry()
    registry.register(spec, adapter)
    return registry


class _FakeAuditRepo:
    """模拟审计仓储相关组件。"""

    def __init__(self) -> None:
        """初始化模拟审计仓储。"""
        self.events: list = []

    async def save(self, event) -> None:  # noqa: ANN001
        """保存模拟审计仓储。

        Args:
            event: 待处理事件。
        """
        self.events.append(event)


@pytest.mark.asyncio
async def test_writeback_success_and_audit() -> None:
    """验证写回成功及审计对应的测试场景。"""
    registry = await _registry_with("conn-wb", "t1")
    audit = _FakeAuditRepo()
    service = TicketWritebackService(registry, audit_repository=audit)
    data = await service.write_back(_ticket())
    assert data == {"refunded": True}
    assert len(audit.events) == 1
    assert audit.events[0].resource_id == "ticket-wb-1"
    assert audit.events[0].action == "ticket.writeback"
    assert audit.events[0].payload["ok"] is True


@pytest.mark.asyncio
async def test_writeback_no_connector_raises() -> None:
    """验证写回无连接器抛出对应的测试场景。"""
    registry = ConnectorRegistry()
    service = TicketWritebackService(registry)
    with pytest.raises(ValueError):
        await service.write_back(_ticket())


@pytest.mark.asyncio
async def test_writeback_failure_raises_and_audits() -> None:
    """验证写回失败抛出及审计对应的测试场景。"""
    registry = await _registry_with("conn-wb-fail", "t1", error=True)
    audit = _FakeAuditRepo()
    service = TicketWritebackService(registry, audit_repository=audit)
    with pytest.raises(RuntimeError):
        await service.write_back(_ticket())
    assert audit.events[0].payload["ok"] is False


@pytest.mark.asyncio
async def test_writeback_uses_resolver() -> None:
    """验证写回使用解析器对应的测试场景。"""
    registry = await _registry_with("conn-resolved", "t1")
    service = TicketWritebackService(registry, connector_resolver=lambda _t: "conn-resolved")
    data = await service.write_back(_ticket())
    assert data == {"refunded": True}
