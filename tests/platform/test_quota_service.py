from __future__ import annotations

from agentforge.platform.application.quota_service import QuotaAwareModelGateway
from agentforge.platform.domain.model import ModelRequest
from agentforge.platform.domain.tenant_quota import TenantQuota


class _StubGateway:
    async def complete(self, request: ModelRequest):
        return {"content": "ok"}


class _StubCost:
    def __init__(self, used: float = 0.0) -> None:
        self._used = used

    async def total_for_tenant(self, tenant_id: str) -> float:
        return self._used

    async def save(self, record) -> None:  # noqa: D102
        pass


class _StubQuotaRepo:
    def __init__(self, quota: TenantQuota | None = None) -> None:
        self._quota = quota

    async def get(self, tenant_id: str) -> TenantQuota | None:
        return self._quota

    async def upsert(self, quota) -> None:
        self._quota = quota

    async def list(self, limit: int = 100) -> list[TenantQuota]:
        return [self._quota] if self._quota else []

    async def delete(self, tenant_id: str) -> None:
        self._quota = None


def _request(tenant_id: str, cost: float) -> ModelRequest:
    return ModelRequest(
        system_prompt="s",
        user_prompt="u",
        metadata={"tenant_id": tenant_id, "estimated_cost": cost},
    )


async def test_global_budget_blocks() -> None:
    gw = QuotaAwareModelGateway(_StubGateway(), _StubCost(used=90.0), 100.0)
    from agentforge.platform.application.quota_service import QuotaExceededError

    try:
        await gw.complete(_request("t1", 20.0))
        raised = False
    except QuotaExceededError:
        raised = True
    assert raised


async def test_tenant_quota_takes_precedence_and_blocks() -> None:
    repo = _StubQuotaRepo(_StubQuota("t1", monthly_limit=50.0))
    gw = QuotaAwareModelGateway(
        _StubGateway(),
        _StubCost(used=40.0),
        1000.0,  # global huge budget, tenant should override
        tenant_quota_repository=repo,
    )
    from agentforge.platform.application.quota_service import QuotaExceededError

    try:
        await gw.complete(_request("t1", 20.0))
        raised = False
    except QuotaExceededError:
        raised = True
    assert raised


async def test_tenant_quota_allows_under_limit() -> None:
    repo = _StubQuotaRepo(_StubQuota("t1", monthly_limit=100.0))
    gw = QuotaAwareModelGateway(
        _StubGateway(),
        _StubCost(used=40.0),
        5.0,
        tenant_quota_repository=repo,
    )
    result = await gw.complete(_request("t1", 20.0))
    assert result == {"content": "ok"}


async def test_disabled_tenant_quota_exempts() -> None:
    quota = _StubQuota("t1", monthly_limit=1.0)
    quota.enabled = False
    repo = _StubQuotaRepo(quota)
    gw = QuotaAwareModelGateway(
        _StubGateway(),
        _StubCost(used=100.0),
        5.0,
        tenant_quota_repository=repo,
    )
    result = await gw.complete(_request("t1", 20.0))
    assert result == {"content": "ok"}


def _StubQuota(tenant_id: str, monthly_limit: float) -> TenantQuota:
    return TenantQuota(
        tenant_id=tenant_id,
        monthly_limit=monthly_limit,
        warning_threshold=0.8,
        hard_limit=1.0,
        enabled=True,
    )