from __future__ import annotations

from agentforge.platform.application.ports import CostRepository
from agentforge.platform.domain.model import ModelRequest, ModelResponse


class QuotaExceededError(RuntimeError):
    pass


class QuotaAwareModelGateway:
    def __init__(self, inner, cost_repository: CostRepository, monthly_budget: float) -> None:
        self._inner = inner
        self._cost_repository = cost_repository
        self._monthly_budget = monthly_budget

    async def complete(self, request: ModelRequest) -> ModelResponse:
        estimated_cost = float(request.metadata.get("estimated_cost", 0.01))
        tenant_id = str(request.metadata.get("tenant_id", ""))
        used = await self._cost_repository.total_for_tenant(tenant_id)
        if used + estimated_cost > self._monthly_budget:
            raise QuotaExceededError("Monthly model budget exceeded")
        return await self._inner.complete(request)
