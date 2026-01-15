"""AgentForge 平台测试层：test_quota_service。

本测试模块验证 test_quota_service 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：_StubGateway、_StubCost、_StubQuotaRepo。
-
主要函数：test_global_budget_blocks、test_tenant_quota_takes_precedence_and_blocks、test_tenant_quota_allows_under_limit、test_disabled_tenant_quota_exempts、test_tenant_hard_limit_blocks_below_full_usage、test_tenant_hard_limit_allows_under_threshold、test_quota_decision_surfaces_on_model_response、test_warning_status_when_crossing_warning_threshold。
"""

from __future__ import annotations

import datetime

from agentforge.platform.application.quota_service import QuotaAwareModelGateway
from agentforge.platform.domain.model import ModelRequest, ModelResponse
from agentforge.platform.domain.tenant_quota import TenantQuota


class _StubGateway:
    """_StubGateway。

    _StubGateway 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

    主要成员：
    - 方法 complete()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def complete(self, request: ModelRequest):
        """执行 complete 对应的逻辑，并返回处理结果。

        Args:
            request: ModelRequest，调用方传入的 request 参数。

        Returns:
            None，函数执行后的结果。
        """
        return {"content": "ok"}


class _StubCost:
    """_StubCost。

    _StubCost 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 total_for_tenant()。
    - 方法 monthly_total_for_tenant()。
    - 方法 save()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, used: float = 0.0, monthly: float | None = None) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            used: float，调用方传入的 used 参数。
            monthly: float | None，调用方传入的 monthly 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._used = used
        self._monthly = used if monthly is None else monthly

    async def total_for_tenant(self, tenant_id: str) -> float:
        """执行 total_for_tenant 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            float，函数执行后的结果。
        """
        return self._used

    async def monthly_total_for_tenant(self, tenant_id: str, now: datetime.datetime) -> float:
        """执行 monthly_total_for_tenant 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            now: datetime.datetime，调用方传入的 now 参数。

        Returns:
            float，函数执行后的结果。
        """
        return self._monthly

    async def save(self, record) -> None:  # noqa: D102
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            record: Any，调用方传入的 record 参数。

        Returns:
            None，函数执行后的结果。
        """
        pass


class _StubQuotaRepo:
    """_StubQuotaRepo。

    _StubQuotaRepo 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 get()。
    - 方法 upsert()。
    - 方法 list()。
    - 方法 delete()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, quota: TenantQuota | None = None) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            quota: TenantQuota | None，调用方传入的 quota 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._quota = quota

    async def get(self, tenant_id: str) -> TenantQuota | None:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            TenantQuota | None，函数执行后的结果。
        """
        return self._quota

    async def upsert(self, quota) -> None:
        """执行 upsert 对应的逻辑，并返回处理结果。

        Args:
            quota: Any，调用方传入的 quota 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._quota = quota

    async def list(self, limit: int = 100) -> list[TenantQuota]:
        """执行 list 对应的核心操作，并保持调用契约稳定。

        Args:
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[TenantQuota]，函数执行后的结果。
        """
        return [self._quota] if self._quota else []

    async def delete(self, tenant_id: str) -> None:
        """执行 delete 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._quota = None


def _request(tenant_id: str, cost: float) -> ModelRequest:
    """执行 _request 对应的逻辑，并返回处理结果。

    Args:
        tenant_id: str，调用方传入的 tenant_id 参数。
        cost: float，调用方传入的 cost 参数。

    Returns:
        ModelRequest，函数执行后的结果。
    """
    return ModelRequest(
        system_prompt="s",
        user_prompt="u",
        metadata={"tenant_id": tenant_id, "estimated_cost": cost},
    )


async def test_global_budget_blocks() -> None:
    """验证 global_budget_blocks 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    gw = QuotaAwareModelGateway(_StubGateway(), _StubCost(used=90.0), 100.0)
    from agentforge.platform.application.quota_service import QuotaExceededError

    try:
        await gw.complete(_request("t1", 20.0))
        raised = False
    except QuotaExceededError:
        raised = True
    assert raised


async def test_tenant_quota_takes_precedence_and_blocks() -> None:
    """验证 tenant_quota_takes_precedence_and_blocks 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    repo = _StubQuotaRepo(_StubQuota("t1", monthly_limit=50.0))
    gw = QuotaAwareModelGateway(
        _StubGateway(),
        _StubCost(used=40.0),
        1000.0,  # 验证租户上下文和隔离约束。
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
    """验证 tenant_quota_allows_under_limit 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
    """验证 disabled_tenant_quota_exempts 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
    """执行 _StubQuota 对应的逻辑，并返回处理结果。

    Args:
        tenant_id: str，调用方传入的 tenant_id 参数。
        monthly_limit: float，调用方传入的 monthly_limit 参数。

    Returns:
        TenantQuota，函数执行后的结果。
    """
    return TenantQuota(
        tenant_id=tenant_id,
        monthly_limit=monthly_limit,
        warning_threshold=0.8,
        hard_limit=1.0,
        enabled=True,
    )


# --- P0-2: hard_limit 真正强制 + 月度判定 + 对账决策 ---


async def test_tenant_hard_limit_blocks_below_full_usage() -> None:
    """验证 tenant_hard_limit_blocks_below_full_usage 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    quota = TenantQuota(
        tenant_id="t1",
        monthly_limit=100.0,
        warning_threshold=0.7,
        hard_limit=0.9,
        enabled=True,
    )
    repo = _StubQuotaRepo(quota)
    # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
    gw = QuotaAwareModelGateway(
        _StubGateway(), _StubCost(monthly=88.0), 9999.0, tenant_quota_repository=repo
    )
    from agentforge.platform.application.quota_service import QuotaExceededError

    try:
        await gw.complete(_request("t1", 5.0))
        raised = False
    except QuotaExceededError:
        raised = True
    assert raised


async def test_tenant_hard_limit_allows_under_threshold() -> None:
    """验证 tenant_hard_limit_allows_under_threshold 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    quota = TenantQuota(
        tenant_id="t1",
        monthly_limit=100.0,
        warning_threshold=0.7,
        hard_limit=0.9,
        enabled=True,
    )
    repo = _StubQuotaRepo(quota)
    gw = QuotaAwareModelGateway(
        _StubGateway(), _StubCost(monthly=80.0), 9999.0, tenant_quota_repository=repo
    )
    result = await gw.complete(_request("t1", 5.0))
    assert result == {"content": "ok"}


async def test_quota_decision_surfaces_on_model_response() -> None:
    """验证 quota_decision_surfaces_on_model_response 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    quota = _StubQuota("t1", monthly_limit=100.0)
    repo = _StubQuotaRepo(quota)

    class _RespGateway:
        """_RespGateway。

        _RespGateway 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

        主要成员：
        - 方法 complete()。

        设计约束：
        - 保持接口稳定，不向调用方暴露不必要的数据结构。
        - 涉及租户、权限、审计或成本的逻辑必须显式处理。
        """

        async def complete(self, request: ModelRequest) -> ModelResponse:
            """执行 complete 对应的逻辑，并返回处理结果。

            Args:
                request: ModelRequest，调用方传入的 request 参数。

            Returns:
                ModelResponse，函数执行后的结果。
            """
            return ModelResponse(
                content="hello",
                model="m",
                provider="p",
                metadata={},
            )

    gw = QuotaAwareModelGateway(
        _RespGateway(), _StubCost(monthly=30.0), 9999.0, tenant_quota_repository=repo
    )
    response: ModelResponse = await gw.complete(_request("t1", 5.0))
    q = response.metadata["quota"]
    assert q["status"] == "active"
    assert q["source"] == "tenant"
    assert q["used_month"] == 30.0
    assert abs(q["effective_limit"] - 100.0) < 1e-6
    assert abs(q["remaining"] - 70.0) < 1e-6


async def test_warning_status_when_crossing_warning_threshold() -> None:
    """验证 warning_status_when_crossing_warning_threshold 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    quota = TenantQuota(
        tenant_id="t1",
        monthly_limit=100.0,
        warning_threshold=0.8,
        hard_limit=1.0,
        enabled=True,
    )
    repo = _StubQuotaRepo(quota)

    class _RespGateway:
        """_RespGateway。

        _RespGateway 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

        主要成员：
        - 方法 complete()。

        设计约束：
        - 保持接口稳定，不向调用方暴露不必要的数据结构。
        - 涉及租户、权限、审计或成本的逻辑必须显式处理。
        """

        async def complete(self, request: ModelRequest) -> ModelResponse:
            """执行 complete 对应的逻辑，并返回处理结果。

            Args:
                request: ModelRequest，调用方传入的 request 参数。

            Returns:
                ModelResponse，函数执行后的结果。
            """
            return ModelResponse(content="ok", model="m", provider="p", metadata={})

    gw = QuotaAwareModelGateway(
        _RespGateway(), _StubCost(monthly=82.0), 9999.0, tenant_quota_repository=repo
    )
    response: ModelResponse = await gw.complete(_request("t1", 1.0))
    assert response.metadata["quota"]["status"] == "warning"


async def test_monthly_window_not_lifetime() -> None:
    """验证 monthly_window_not_lifetime 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    quota = _StubQuota("t1", monthly_limit=10.0)
    repo = _StubQuotaRepo(quota)
    # 当月已用 9，cost=2 -> 9+2=11 > 10 -> blocked（当月窗口）
    gw = QuotaAwareModelGateway(
        _StubGateway(), _StubCost(monthly=9.0), 9999.0, tenant_quota_repository=repo
    )
    from agentforge.platform.application.quota_service import QuotaExceededError

    try:
        await gw.complete(_request("t1", 2.0))
        raised = False
    except QuotaExceededError:
        raised = True
    assert raised
