"""AgentForge 平台应用服务层：model_router。

本模块定义 model_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：ModelRouter。
"""

from __future__ import annotations

from agentforge.platform.domain.model import ModelProfile


class ModelRouter:
    """ModelRouter。

    ModelRouter 定义 HTTP 路由，负责参数校验、鉴权、调用应用服务并组织响应。

    主要成员：
    - 方法 select()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, profiles: list[ModelProfile]) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            profiles: list[ModelProfile]，调用方传入的 profiles 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if not profiles:
            raise ValueError("At least one model profile is required")
        self._profiles = profiles

    def select(self, task_type: str = "general", strategy: str = "balanced") -> ModelProfile:
        """执行 select 对应的逻辑，并返回处理结果。

        Args:
            task_type: str，调用方传入的 task_type 参数。
            strategy: str，调用方传入的 strategy 参数。

        Returns:
            ModelProfile，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        candidates = [profile for profile in self._profiles if profile.is_available]
        if not candidates:
            raise ValueError("No available model profiles")
        specialized = [profile for profile in candidates if task_type in profile.task_types]
        if specialized:
            candidates = specialized
        if strategy == "cheapest":
            return min(candidates, key=lambda profile: profile.cost_per_1k_tokens)
        if strategy == "fastest":
            return min(candidates, key=lambda profile: profile.avg_latency_ms)
        if strategy == "capable":
            return max(candidates, key=lambda profile: profile.capability_score)
        return max(
            candidates,
            key=lambda profile: profile.capability_score - profile.cost_per_1k_tokens,
        )
