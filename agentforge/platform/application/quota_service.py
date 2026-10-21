"""配额服务模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agentforge.platform.application.ports import CostRepository
from agentforge.platform.domain.model import ModelRequest, ModelResponse
from agentforge.platform.domain.tenant_quota import TenantQuota
from agentforge.platform.domain.usage import UsageMetric
from agentforge.platform.sdk.ports import UsagePort


class QuotaExceededError(RuntimeError):
    """配额超出错误相关组件。"""

    pass


class QuotaDecision:
    """配额决策领域组件。"""

    def __init__(
        self,
        status: str,
        used: float,
        effective_limit: float,
        remaining: float,
        source: str,
    ) -> None:
        """初始化 QuotaDecision。

        Args:
            status: 目标状态。
            used: 已使用。
            effective_limit: 限制。
            remaining: 输入参数。
            source: 调用或事件来源。
        """
        self.status = status
        self.used = used
        self.effective_limit = effective_limit
        self.remaining = remaining
        self.source = source

    def to_dict(self) -> dict:
        """处理到字典。

        Returns:
            结构化结果字典。
        """
        return {
            "status": self.status,
            "source": self.source,
            "used_month": round(self.used, 4),
            "effective_limit": round(self.effective_limit, 4),
            "remaining": round(self.remaining, 4),
        }


class QuotaAwareModelGateway:
    """配额模型网关抽象。"""

    def __init__(
        self,
        inner,
        cost_repository: CostRepository,
        monthly_budget: float,
        tenant_quota_repository=None,
    ) -> None:
        """初始化 QuotaAwareModelGateway。

        Args:
            inner: 输入参数。
            cost_repository: 成本仓储。
            monthly_budget: 月度预算。
            tenant_quota_repository: 租户配额仓储。
        """
        self._inner = inner
        self._cost_repository = cost_repository
        self._monthly_budget = monthly_budget
        self._tenant_quota_repository = tenant_quota_repository
        self._usage_meter: UsagePort | None = None

    def set_usage_meter(self, usage_meter: UsagePort) -> None:
        """设置用量计量。

        Args:
            usage_meter: 用量计量。
        """
        self._usage_meter = usage_meter

    async def _resolve_budget(
        self, tenant_id: str
    ) -> tuple[float, float, bool, str, TenantQuota | None]:
        """解析预算。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果元组。
        """
        if self._tenant_quota_repository is not None:
            quota: TenantQuota | None = await self._tenant_quota_repository.get(tenant_id)
            if quota is not None:
                if not quota.enabled:
                    return float("inf"), 1.0, False, "tenant-exempt", quota
                if quota.monthly_limit <= 0:
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
        """处理已使用用于周期。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            数值结果。
        """
        monthly = getattr(self._cost_repository, "monthly_total_for_tenant", None)
        if monthly is not None:
            return await monthly(tenant_id, datetime.now(timezone.utc))
        return await self._cost_repository.total_for_tenant(tenant_id)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """完成配额模型。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            模型响应结果。

        Raises:
            QuotaExceededError: 操作无法完成时抛出。
        """
        estimated_cost = float(request.metadata.get("estimated_cost", 0.01))
        tenant_id = str(request.metadata.get("tenant_id", ""))
        effective_limit, hard_fraction, enforce, source, quota = await self._resolve_budget(
            tenant_id
        )
        decision: QuotaDecision | None = None
        if enforce:
            used = await self._used_for_period(tenant_id)
            # 验证配额控制，确保预算和硬限额生效。
            if effective_limit != float("inf") and used + estimated_cost > effective_limit:
                decision = QuotaDecision(
                    "blocked", used, effective_limit, max(0.0, effective_limit - used), source
                )
                raise QuotaExceededError(
                    "Quota exceeded: spent %.2f / %.2f (%s)" % (used, effective_limit, source)
                )
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
        tenant_id = str(request.metadata.get("tenant_id") or "").strip()
        if isinstance(response, dict):
            token_count = int(response.get("input_tokens", 0)) + int(
                response.get("output_tokens", 0)
            )
            model_name = str(response.get("model", ""))
            provider_name = str(response.get("provider", ""))
        else:
            token_count = int(getattr(response, "input_tokens", 0)) + int(
                getattr(response, "output_tokens", 0)
            )
            model_name = str(response.model)
            provider_name = str(response.provider)
        if self._usage_meter is not None and tenant_id and token_count > 0:
            idempotency_key = str(
                request.metadata.get("trace_id")
                or request.metadata.get("idempotency_key")
                or f"model-{uuid4()}"
            )
            await self._usage_meter.record(
                tenant_id=tenant_id,
                metric=UsageMetric.MODEL_TOKENS,
                quantity=token_count,
                source="model-gateway",
                idempotency_key=idempotency_key,
                metadata={"model": model_name, "provider": provider_name},
            )
        if decision is not None:
            meta = dict(getattr(response, "metadata", {}) or {})
            meta["quota"] = decision.to_dict()
            if hasattr(response, "model_copy"):
                return response.model_copy(update={"metadata": meta})
        return response
