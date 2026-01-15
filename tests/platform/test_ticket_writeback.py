"""AgentForge 平台测试层：test_ticket_writeback。

本测试模块验证 test_ticket_writeback 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：_FakeAuditRepo。
-
主要函数：test_writeback_success_and_audit、test_writeback_no_connector_raises、test_writeback_failure_raises_and_audits、test_writeback_uses_resolver。
"""

import pytest

from agentforge.platform.application.connector_registry import ConnectorRegistry
from agentforge.platform.application.openapi_adapter import OpenAPIAdapter
from agentforge.platform.application.ticket_writeback import TicketWritebackService
from agentforge.platform.domain.connector import (
    ConnectorKind,
    ConnectorRiskLevel,
    ConnectorSpec,
)
from agentforge.platform.domain.ticket import (
    RiskLevel,
    Ticket,
    TicketPriority,
    TicketStatus,
)


def _ticket() -> Ticket:
    """执行 _ticket 对应的逻辑，并返回处理结果。

    Returns:
        Ticket，函数执行后的结果。
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
    """执行 _registry_with 对应的逻辑，并返回处理结果。

    Args:
        connector_id: str，调用方传入的 connector_id 参数。
        tenant_id: str，调用方传入的 tenant_id 参数。
        error: bool，调用方传入的 error 参数。

    Returns:
        ConnectorRegistry，函数执行后的结果。

    Raises:
        RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
    """

    async def _request(method, url, **kw):  # noqa: ANN001, ANN202
        """执行 _request 对应的逻辑，并返回处理结果。

        Args:
            method: Any，调用方传入的 method 参数。
            url: Any，调用方传入的 url 参数。
            **kw: Any，调用方传入的 **kw 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
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
    """_FakeAuditRepo。

    _FakeAuditRepo 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 save()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self.events: list = []

    async def save(self, event) -> None:  # noqa: ANN001
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            event: Any，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.events.append(event)


@pytest.mark.asyncio
async def test_writeback_success_and_audit() -> None:
    """验证 writeback_success_and_audit 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
    """验证 writeback_no_connector_raises 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    registry = ConnectorRegistry()
    service = TicketWritebackService(registry)
    with pytest.raises(ValueError):
        await service.write_back(_ticket())


@pytest.mark.asyncio
async def test_writeback_failure_raises_and_audits() -> None:
    """验证 writeback_failure_raises_and_audits 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    registry = await _registry_with("conn-wb-fail", "t1", error=True)
    audit = _FakeAuditRepo()
    service = TicketWritebackService(registry, audit_repository=audit)
    with pytest.raises(RuntimeError):
        await service.write_back(_ticket())
    assert audit.events[0].payload["ok"] is False


@pytest.mark.asyncio
async def test_writeback_uses_resolver() -> None:
    """验证 writeback_uses_resolver 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    registry = await _registry_with("conn-resolved", "t1")
    service = TicketWritebackService(registry, connector_resolver=lambda _t: "conn-resolved")
    data = await service.write_back(_ticket())
    assert data == {"refunded": True}
