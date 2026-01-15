"""AgentForge 平台测试层：test_policies_router。

本测试模块验证 test_policies_router 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_policies_list_and_revision、test_policies_reload_success_bumps_revision、test_policies_reload_bad_policy_fails_closed_keeps_old、test_policies_reload_bad_body_422。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.runtime import build_memory_container

# 常量：VALID_POLICY。
VALID_POLICY = {
    "name": "write-ticket",
    "tenant_id": "tenant-a",
    "action": "ticket:write",
    "risk_level": "high",
    "allowed_roles": ["support_admin"],
    "require_approval": True,
    "enabled": True,
}


@pytest.mark.asyncio
async def test_policies_list_and_revision() -> None:
    """验证 policies_list_and_revision 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    container = build_memory_container()
    app = create_platform_app(container)
    client = TestClient(app)

    resp = client.get("/v1/policies", params={"tenant_id": "tenant-a"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == "tenant-a"
    assert data["source_revision"] >= 0
    assert "policies" in data

    rev = client.get("/v1/policies/revision")
    assert rev.status_code == 200
    assert rev.json()["source_revision"] == data["source_revision"]


@pytest.mark.asyncio
async def test_policies_reload_success_bumps_revision() -> None:
    """验证 policies_reload_success_bumps_revision 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    container = build_memory_container()
    app = create_platform_app(container)
    client = TestClient(app)

    base = client.get("/v1/policies/revision").json()["source_revision"]

    resp = client.post("/v1/policies/reload", json={"policies": [VALID_POLICY]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["revision"] == base + 1
    assert data["count"] == 1

    # reload 后该租户能看到新策略
    listed = client.get("/v1/policies", params={"tenant_id": "tenant-a"}).json()
    assert listed["source_revision"] == base + 1
    assert any(p["action"] == "ticket:write" for p in listed["policies"])


@pytest.mark.asyncio
async def test_policies_reload_bad_policy_fails_closed_keeps_old() -> None:
    """验证 policies_reload_bad_policy_fails_closed_keeps_old 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    container = build_memory_container()
    app = create_platform_app(container)
    client = TestClient(app)

    # 先加载一份好策略
    ok = client.post("/v1/policies/reload", json={"policies": [VALID_POLICY]})
    assert ok.status_code == 200
    good_rev = ok.json()["revision"]

    # 坏配置：含未知字段（ActionPolicy extra=forbid）
    bad = dict(VALID_POLICY, unknown_field="surprise")
    resp = client.post("/v1/policies/reload", json={"policies": [bad]})
    assert resp.status_code == 422

    # revision 未变，旧策略仍在
    rev = client.get("/v1/policies/revision").json()["source_revision"]
    assert rev == good_rev
    listed = client.get("/v1/policies", params={"tenant_id": "tenant-a"}).json()
    assert any(p["action"] == "ticket:write" for p in listed["policies"])


@pytest.mark.asyncio
async def test_policies_reload_bad_body_422() -> None:
    """验证 policies_reload_bad_body_422 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    container = build_memory_container()
    app = create_platform_app(container)
    client = TestClient(app)

    # 缺少 policies 字段
    resp = client.post("/v1/policies/reload", json={})
    assert resp.status_code == 422

    # policies 不是 list
    resp2 = client.post("/v1/policies/reload", json={"policies": "not-a-list"})
    assert resp2.status_code == 422
