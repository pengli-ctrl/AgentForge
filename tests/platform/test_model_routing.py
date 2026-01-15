"""AgentForge 平台测试层：test_model_routing。

本测试模块验证 test_model_routing 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：test_model_router_selects_expected_profiles、test_quota_gateway_rejects_over_budget。
"""

import pytest

from agentforge.platform.application.model_router import ModelRouter
from agentforge.platform.application.quota_service import QuotaAwareModelGateway, QuotaExceededError
from agentforge.platform.domain.cost import CostRecord
from agentforge.platform.domain.model import ModelProfile, ModelRequest
from agentforge.platform.infrastructure.llm.static_gateway import StaticModelGateway
from agentforge.platform.infrastructure.memory_cost_repository import MemoryCostRepository


def test_model_router_selects_expected_profiles() -> None:
    """验证 model_router_selects_expected_profiles 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    router = ModelRouter(
        [
            ModelProfile(
                name="cheap",
                provider="test",
                model_id="cheap-model",
                capability_score=5.0,
                cost_per_1k_tokens=0.001,
                avg_latency_ms=1000,
                task_types=["general"],
            ),
            ModelProfile(
                name="capable",
                provider="test",
                model_id="capable-model",
                capability_score=9.0,
                cost_per_1k_tokens=0.02,
                avg_latency_ms=2000,
                task_types=["drafting"],
            ),
        ]
    )
    assert router.select("drafting", "capable").name == "capable"
    assert router.select("general", "cheapest").name == "cheap"


@pytest.mark.asyncio
async def test_quota_gateway_rejects_over_budget() -> None:
    """验证 quota_gateway_rejects_over_budget 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    cost_repository = MemoryCostRepository()
    await cost_repository.save(
        CostRecord(
            tenant_id="tenant-1",
            task_id="task-1",
            model_name="test",
            provider="test",
            input_tokens=1,
            output_tokens=1,
            amount=0.5,
        )
    )
    gateway = QuotaAwareModelGateway(StaticModelGateway(), cost_repository, monthly_budget=0.51)
    request = ModelRequest(
        system_prompt="system",
        user_prompt="user",
        metadata={"tenant_id": "tenant-1", "estimated_cost": 0.02},
    )
    with pytest.raises(QuotaExceededError):
        await gateway.complete(request)
