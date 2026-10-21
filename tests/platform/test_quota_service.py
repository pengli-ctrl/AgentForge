"""配额服务测试模块。

本测试模块验证 test_quota_service 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：_StubGateway、_StubCost、_StubQuotaRepo。
-
主要函数：test_global_budget_blocks、test_tenant_quota_takes_precedence_and_blocks、test_tenant_quota_a
    llows_under_limit、test_disabled_tenant_quota_exempts、test_tenant_hard_limit_blocks_below_ful
    l_usage、test_tenant_hard_limit_allows_under_threshold、test_quota_decision_surfaces_on_model_
    response、test_warning_status_when_crossing_warning_threshold。
"""

from __future__ import annotations

import datetime

from agentforge.platform.application.quota_service import QuotaAwareModelGateway
from agentforge.platform.domain.model import ModelRequest, ModelResponse
from agentforge.platform.domain.tenant_quota import TenantQuota


class _StubGateway:
    """桩网关抽象。"""

    async def complete(self, request: ModelRequest):
        """完成桩。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            处理结果。
        """
        return {"content": "ok"}


class _StubCost:
    """桩成本相关组件。"""

    def __init__(self, used: float = 0.0, monthly: float | None = None) -> None:
        """初始化桩成本。

        Args:
            used: 已使用。
            monthly: 月度。
        """
        self._used = used
        self._monthly = used if monthly is None else monthly

    async def total_for_tenant(self, tenant_id: str) -> float:
        """获取租户的总计。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            数值结果。
        """
        return self._used

    async def monthly_total_for_tenant(self, tenant_id: str, now: datetime.datetime) -> float:
        """获取租户的月度总计。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            now: 输入参数。

        Returns:
            数值结果。
        """
        return self._monthly

    async def save(self, record) -> None:  # noqa: D102
        """保存桩成本。

        Args:
            record: 待处理的领域记录。
        """
        pass


class _StubQuotaRepo:
    """桩配额仓储相关组件。"""

    def __init__(self, quota: TenantQuota | None = None) -> None:
        """初始化桩配额仓储。

        Args:
            quota: 配额配置。
        """
        self._quota = quota

    async def get(self, tenant_id: str) -> TenantQuota | None:
        """获取桩配额仓储。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            租户配额无结果。
        """
        return self._quota

    async def upsert(self, quota) -> None:
        """新建或更新桩配额仓储。

        Args:
            quota: 配额配置。
        """
        self._quota = quota

    async def list(self, limit: int = 100) -> list[TenantQuota]:
        """查询桩配额仓储。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        return [self._quota] if self._quota else []

    async def delete(self, tenant_id: str) -> None:
        """删除桩配额仓储。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
        """
        self._quota = None


def _request(tenant_id: str, cost: float) -> ModelRequest:
    """处理请求。

    Args:
        tenant_id: 租户 ID，用于数据隔离。
        cost: 成本。

    Returns:
        模型请求结果。
    """
    return ModelRequest(
        system_prompt="s",
        user_prompt="u",
        metadata={"tenant_id": tenant_id, "estimated_cost": cost},
    )


async def test_global_budget_blocks() -> None:
    """验证全局预算阻止对应的测试场景。"""
    gw = QuotaAwareModelGateway(_StubGateway(), _StubCost(used=90.0), 100.0)
    from agentforge.platform.application.quota_service import QuotaExceededError

    try:
        await gw.complete(_request("t1", 20.0))
        raised = False
    except QuotaExceededError:
        raised = True
    assert raised


async def test_tenant_quota_takes_precedence_and_blocks() -> None:
    """验证租户配额及阻止对应的测试场景。"""
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
    """验证租户配额允许在下限制对应的测试场景。"""
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
    """验证停用租户配额对应的测试场景。"""
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
    """处理桩配额。

    Args:
        tenant_id: 租户 ID，用于数据隔离。
        monthly_limit: 月度限制。

    Returns:
        租户配额结果。
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
    """验证租户硬限制阻止以下完整用量对应的测试场景。"""
    quota = TenantQuota(
        tenant_id="t1",
        monthly_limit=100.0,
        warning_threshold=0.7,
        hard_limit=0.9,
        enabled=True,
    )
    repo = _StubQuotaRepo(quota)
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
    """验证租户硬限制允许在下阈值对应的测试场景。"""
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
    """验证配额决策时模型响应对应的测试场景。"""
    quota = _StubQuota("t1", monthly_limit=100.0)
    repo = _StubQuotaRepo(quota)

    class _RespGateway:
        """响应网关抽象。"""

        async def complete(self, request: ModelRequest) -> ModelResponse:
            """完成响应。

            Args:
                request: 当前 HTTP 请求。

            Returns:
                模型响应结果。
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
    """验证警告状态当警告阈值对应的测试场景。"""
    quota = TenantQuota(
        tenant_id="t1",
        monthly_limit=100.0,
        warning_threshold=0.8,
        hard_limit=1.0,
        enabled=True,
    )
    repo = _StubQuotaRepo(quota)

    class _RespGateway:
        """响应网关抽象。"""

        async def complete(self, request: ModelRequest) -> ModelResponse:
            """完成响应。

            Args:
                request: 当前 HTTP 请求。

            Returns:
                模型响应结果。
            """
            return ModelResponse(content="ok", model="m", provider="p", metadata={})

    gw = QuotaAwareModelGateway(
        _RespGateway(), _StubCost(monthly=82.0), 9999.0, tenant_quota_repository=repo
    )
    response: ModelResponse = await gw.complete(_request("t1", 1.0))
    assert response.metadata["quota"]["status"] == "warning"


async def test_monthly_window_not_lifetime() -> None:
    """验证月度窗口不对应的测试场景。"""
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
