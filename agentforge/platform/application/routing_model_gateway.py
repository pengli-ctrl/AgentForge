"""AgentForge 平台应用服务层：routing_model_gateway。

本模块封装 routing_model_gateway 对应外部系统或基础设施协议，提供稳定、可替换的适配接口。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：RoutingModelGateway。
"""

from __future__ import annotations

from agentforge.platform.application.model_router import ModelRouter
from agentforge.platform.domain.model import ModelRequest, ModelResponse


class RoutingModelGateway:
    """RoutingModelGateway。

    RoutingModelGateway 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

    主要成员：
    - 方法 complete()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, router: ModelRouter, inner) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            router: ModelRouter，调用方传入的 router 参数。
            inner: Any，调用方传入的 inner 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._router = router
        self._inner = inner

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """执行 complete 对应的逻辑，并返回处理结果。

        Args:
            request: ModelRequest，调用方传入的 request 参数。

        Returns:
            ModelResponse，函数执行后的结果。
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
