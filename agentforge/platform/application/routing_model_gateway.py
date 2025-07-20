from __future__ import annotations

from agentforge.platform.application.model_router import ModelRouter
from agentforge.platform.domain.model import ModelRequest, ModelResponse


class RoutingModelGateway:
    def __init__(self, router: ModelRouter, inner) -> None:
        self._router = router
        self._inner = inner

    async def complete(self, request: ModelRequest) -> ModelResponse:
        task_type = str(request.metadata.get("task_type", "general"))
        strategy = str(request.metadata.get("strategy", "balanced"))
        profile = self._router.select(task_type=task_type, strategy=strategy)
        routed_request = request.model_copy(update={"model": profile.model_id})
        response = await self._inner.complete(routed_request)
        return response.model_copy(
            update={
                "model": profile.name,
                "provider": profile.provider,
                "metadata": {**response.metadata, "model_profile": profile.name},
            }
        )
