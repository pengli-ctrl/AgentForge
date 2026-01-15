"""AgentForge 平台测试层：test_console_api。

本测试模块验证 test_console_api 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：test_quota_crud、test_console_overview。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.domain.cost import CostRecord
from agentforge.platform.infrastructure.memory_cost_repository import MemoryCostRepository
from agentforge.platform.runtime import build_memory_container


def _client():
    """执行 _client 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
    container = build_memory_container()
    app = create_platform_app(container)
    return container, TestClient(app)


def test_quota_crud() -> None:
    """验证 quota_crud 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    container, client = _client()
    r = client.put(
        "/v1/quotas/t1",
        json={
            "monthly_limit": 100.0,
            "warning_threshold": 0.8,
            "hard_limit": 1.0,
            "enabled": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["monthly_limit"] == 100.0

    got = client.get("/v1/quotas/t1").json()
    assert got["configured"] is True
    assert got["usage"]["status"] in {"active", "warning", "blocked"}

    listed = client.get("/v1/quotas").json()
    assert [q["tenant_id"] for q in listed["quotas"]] == ["t1"]

    deleted = client.delete("/v1/quotas/t1").json()
    assert deleted["deleted"] == "t1"
    assert client.get("/v1/quotas/t1").json()["configured"] is False


def test_console_overview() -> None:
    """验证 console_overview 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    container, client = _client()
    client.put(
        "/v1/quotas/t1",
        json={"monthly_limit": 100.0, "warning_threshold": 0.8, "hard_limit": 1.0, "enabled": True},
    )
    assert isinstance(container.cost_repository, MemoryCostRepository)
    container.cost_repository.records.append(
        CostRecord(
            tenant_id="t1",
            task_id="task-1",
            model_name="gpt-x",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            amount=12.5,
            created_at=datetime.now(timezone.utc),
        )
    )

    overview = client.get("/v1/console/overview", params={"tenant_id": "t1"}).json()
    assert overview["tenant_id"] == "t1"
    assert overview["quota"]["configured"] is True
    assert overview["cost"]["used"] == 12.5
    assert "dlq" in overview
    assert "audit" in overview
