from __future__ import annotations

from agentforge.platform.application.ports import CostRepository
from agentforge.platform.domain.model import ModelRequest, ModelResponse
from agentforge.platform.domain.tenant_quota import TenantQuota


class QuotaExceededError(RuntimeError):
    pass


class QuotaAwareModelGateway:
    def __init__(
        self,
        inner,
        cost_repository: CostRepository,
        monthly_budget: float,
        tenant_quota_repository=None,
    ) -> None:
        self._inner = inner
        self._cost_repository = cost_repository
        self._monthly_budget = monthly_budget
        self._tenant_quota_repository = tenant_quota_repository

    async def _resolve_budget(self, tenant_id: str) -> tuple[float, bool]:
        """Return (effective budget, enforce) for a tenant.

        When a tenant-specific quota exists it takes precedence; otherwise the
        global monthly budget applies. ``enforce`` is False when the tenant is
        explicitly exempted (quota.enabled=False).
        """
        if self._tenant_quota_repository is not None:
            quota: TenantQuota | None = await self._tenant_quota_repository.get(tenant_id)
            if quota is not None:
                if not quota.enabled:
                    return 0.0, False
                return quota.monthly_limit, True
        return self._monthly_budget, True

    async def complete(self, request: ModelRequest) -> ModelResponse:
        estimated_cost = float(request.metadata.get("estimated_cost", 0.01))
        tenant_id = str(request.metadata.get("tenant_id", ""))
        budget, enforce = await self._resolve_budget(tenant_id)
        if enforce:
            used = await self._cost_repository.total_for_tenant(tenant_id)
            if used + estimated_cost > budget:
                raise QuotaExceededError("Monthly model budget exceeded")
        return await self._inner.complete(request)
