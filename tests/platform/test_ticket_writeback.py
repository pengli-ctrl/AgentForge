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
    async def _request(method, url, **kw):  # noqa: ANN001, ANN202
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
    def __init__(self) -> None:
        self.events: list = []

    async def save(self, event) -> None:  # noqa: ANN001
        self.events.append(event)


@pytest.mark.asyncio
async def test_writeback_success_and_audit() -> None:
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
    registry = ConnectorRegistry()
    service = TicketWritebackService(registry)
    with pytest.raises(ValueError):
        await service.write_back(_ticket())


@pytest.mark.asyncio
async def test_writeback_failure_raises_and_audits() -> None:
    registry = await _registry_with("conn-wb-fail", "t1", error=True)
    audit = _FakeAuditRepo()
    service = TicketWritebackService(registry, audit_repository=audit)
    with pytest.raises(RuntimeError):
        await service.write_back(_ticket())
    assert audit.events[0].payload["ok"] is False


@pytest.mark.asyncio
async def test_writeback_uses_resolver() -> None:
    registry = await _registry_with("conn-resolved", "t1")
    service = TicketWritebackService(registry, connector_resolver=lambda _t: "conn-resolved")
    data = await service.write_back(_ticket())
    assert data == {"refunded": True}
