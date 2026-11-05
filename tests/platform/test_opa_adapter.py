"""提供架构升级适配。"""
import httpx
import pytest

from agentforge.platform.domain.authorization import AuthorizationOutcome
from agentforge.platform.infrastructure.authz.opa_adapter import OPAPolicyAdapter


@pytest.mark.asyncio
async def test_opa_adapter_maps_allow_decision() -> None:
    """提供架构升级适配。
    """
    def handler(request: httpx.Request) -> httpx.Response:
        """提供架构升级适配。

        Args:
            request: 输入参数。

        Returns:
    处理结果。
        """
        assert request.url.path.endswith("/v1/data/agentforge/allow")
        return httpx.Response(200, json={"result": {"outcome": "allowed", "reasons": []}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OPAPolicyAdapter("http://opa:8181", client=client)
    decision = await adapter.authorize(tenant_id="t1", principal="u1", action="expense.claim.approve", resource_type="expense_claim", resource_id="c1")
    assert decision.outcome == AuthorizationOutcome.ALLOWED
    await client.aclose()


@pytest.mark.asyncio
async def test_opa_adapter_maps_requires_approval() -> None:
    """提供架构升级适配。
    """
    def handler(request: httpx.Request) -> httpx.Response:
        """提供架构升级适配。

        Args:
            request: 输入参数。

        Returns:
    处理结果。
        """
        return httpx.Response(200, json={"result": {"outcome": "requires_approval", "reasons": ["high_risk"]}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OPAPolicyAdapter("http://opa:8181", client=client)
    decision = await adapter.authorize(tenant_id="t1", principal="u1", action="ticket.writeback", resource_type="ticket", resource_id="x1")
    assert decision.outcome == AuthorizationOutcome.REQUIRES_APPROVAL
    assert decision.reasons == ["high_risk"]
    await client.aclose()
