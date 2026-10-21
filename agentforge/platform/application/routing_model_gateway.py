"""模型网关模块。"""

from __future__ import annotations

from agentforge.platform.application.model_router import ModelRouter
from agentforge.platform.domain.model import ModelRequest, ModelResponse


class RoutingModelGateway:
    """路由模型网关抽象。"""

    def __init__(self, router: ModelRouter, inner) -> None:
        """初始化 RoutingModelGateway。

        Args:
            router: 路由。
            inner: 输入参数。
        """
        self._router = router
        self._inner = inner

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """完成路由模型。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            模型响应结果。
        """
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
