"""AgentForge 平台应用服务层：quota_service。

本模块实现 quota_service 应用服务，编排多个领域对象和基础设施组件完成业务流程。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：QuotaExceededError、QuotaDecision、QuotaAwareModelGateway。
"""

from __future__ import annotations

from datetime import datetime, timezone

from agentforge.platform.application.ports import CostRepository
from agentforge.platform.domain.model import ModelRequest, ModelResponse
from agentforge.platform.domain.tenant_quota import TenantQuota


class QuotaExceededError(RuntimeError):
    """QuotaExceededError。

    QuotaExceededError 封装相关领域行为，保持职责单一并降低调用方复杂度。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    pass


class QuotaDecision:
    """QuotaDecision。

    QuotaDecision 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 to_dict()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        status: str,
        used: float,
        effective_limit: float,
        remaining: float,
        source: str,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            status: str，调用方传入的 status 参数。
            used: float，调用方传入的 used 参数。
            effective_limit: float，调用方传入的 effective_limit 参数。
            remaining: float，调用方传入的 remaining 参数。
            source: str，调用方传入的 source 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.status = status
        self.used = used
        self.effective_limit = effective_limit
        self.remaining = remaining
        self.source = source

    def to_dict(self) -> dict:
        """执行 to_dict 对应的逻辑，并返回处理结果。

        Returns:
            dict，函数执行后的结果。
        """
        return {
            "status": self.status,
            "source": self.source,
            "used_month": round(self.used, 4),
            "effective_limit": round(self.effective_limit, 4),
            "remaining": round(self.remaining, 4),
        }


class QuotaAwareModelGateway:
    """QuotaAwareModelGateway。

    QuotaAwareModelGateway 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

    主要成员：
    - 方法 complete()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        inner,
        cost_repository: CostRepository,
        monthly_budget: float,
        tenant_quota_repository=None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            inner: Any，调用方传入的 inner 参数。
            cost_repository: CostRepository，调用方传入的 cost_repository 参数。
            monthly_budget: float，调用方传入的 monthly_budget 参数。
            tenant_quota_repository: Any，调用方传入的 tenant_quota_repository 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._inner = inner
        self._cost_repository = cost_repository
        self._monthly_budget = monthly_budget
        self._tenant_quota_repository = tenant_quota_repository

    async def _resolve_budget(
        self, tenant_id: str
    ) -> tuple[float, float, bool, str, TenantQuota | None]:
        """执行 _resolve_budget 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            tuple[float, float, bool, str, TenantQuota | None]，函数执行后的结果。
        """
        if self._tenant_quota_repository is not None:
            quota: TenantQuota | None = await self._tenant_quota_repository.get(tenant_id)
            if quota is not None:
                if not quota.enabled:
                    return float("inf"), 1.0, False, "tenant-exempt", quota
                if quota.monthly_limit <= 0:
                    # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
                    # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
                    return (
                        self._monthly_budget,
                        1.0,
                        True,
                        "global",
                        quota,
                    )
                effective = quota.monthly_limit * quota.hard_limit
                return effective, quota.hard_limit, True, "tenant", quota
        return self._monthly_budget, 1.0, True, "global", None

    async def _used_for_period(self, tenant_id: str) -> float:
        """执行 _used_for_period 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            float，函数执行后的结果。
        """
        monthly = getattr(self._cost_repository, "monthly_total_for_tenant", None)
        if monthly is not None:
            return await monthly(tenant_id, datetime.now(timezone.utc))
        return await self._cost_repository.total_for_tenant(tenant_id)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """执行 complete 对应的逻辑，并返回处理结果。

        Args:
            request: ModelRequest，调用方传入的 request 参数。

        Returns:
            ModelResponse，函数执行后的结果。

        Raises:
            QuotaExceededError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        estimated_cost = float(request.metadata.get("estimated_cost", 0.01))
        tenant_id = str(request.metadata.get("tenant_id", ""))
        effective_limit, hard_fraction, enforce, source, quota = await self._resolve_budget(
            tenant_id
        )
        decision: QuotaDecision | None = None
        if enforce:
            used = await self._used_for_period(tenant_id)
            # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
            # 验证配额控制，确保预算和硬限额生效。
            if effective_limit != float("inf") and used + estimated_cost > effective_limit:
                decision = QuotaDecision(
                    "blocked", used, effective_limit, max(0.0, effective_limit - used), source
                )
                raise QuotaExceededError(
                    "Quota exceeded: spent %.2f / %.2f (%s)" % (used, effective_limit, source)
                )
            # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
            # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
            if (
                source == "tenant"
                and quota is not None
                and quota.monthly_limit > 0
                and (used + estimated_cost) >= quota.monthly_limit * quota.warning_threshold
            ):
                decision = QuotaDecision(
                    "warning",
                    used,
                    effective_limit,
                    max(0.0, effective_limit - used),
                    source,
                )
            else:
                decision = QuotaDecision(
                    "active",
                    used,
                    effective_limit,
                    max(0.0, effective_limit - used),
                    source,
                )
        response = await self._inner.complete(request)
        if decision is not None:
            meta = dict(getattr(response, "metadata", {}) or {})
            meta["quota"] = decision.to_dict()
            if hasattr(response, "model_copy"):
                return response.model_copy(update={"metadata": meta})
        return response
