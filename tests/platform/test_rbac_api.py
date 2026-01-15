"""AgentForge 平台测试层：test_rbac_api。

本测试模块验证 test_rbac_api 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_create_role_and_list、test_set_permissions_and_assign、test_assign_unknown_role_404、test_authorize_endpoint。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.runtime import build_memory_container


def _client() -> TestClient:
    """执行 _client 对应的逻辑，并返回处理结果。

    Returns:
        TestClient，函数执行后的结果。
    """
    container = build_memory_container()
    app = create_platform_app(container)
    return TestClient(app)


def test_create_role_and_list() -> None:
    """验证 create_role_and_list 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    client = _client()
    r = client.post("/v1/rbac/roles", params={"tenant_id": "t1", "name": "support_admin"})
    assert r.status_code == 200
    role = r.json()
    assert role["tenant_id"] == "t1"
    assert role["name"] == "support_admin"

    listed = client.get("/v1/rbac/roles", params={"tenant_id": "t1"}).json()
    role_ids = [x["name"] for x in listed["roles"]]
    assert "support_admin" in role_ids


def test_set_permissions_and_assign() -> None:
    """验证 set_permissions_and_assign 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    client = _client()
    role = client.post("/v1/rbac/roles", params={"tenant_id": "t1", "name": "support_agent"}).json()
    role_id = role["role_id"]

    setp = client.post(
        f"/v1/rbac/roles/{role_id}/permissions",
        params={"tenant_id": "t1"},
        json={"permissions": ["ticket.read", "ticket.reply"]},
    )
    assert setp.status_code == 200
    assert set(setp.json()["permissions"]) == {"ticket.read", "ticket.reply"}

    asg = client.post(
        "/v1/rbac/assignments",
        params={"tenant_id": "t1", "user_id": "user-1", "role_id": role_id},
    )
    assert asg.status_code == 200
    assert asg.json()["user_id"] == "user-1"

    mine = client.get(
        "/v1/rbac/assignments", params={"tenant_id": "t1", "user_id": "user-1"}
    ).json()
    assert len(mine["assignments"]) == 1


def test_assign_unknown_role_404() -> None:
    """验证 assign_unknown_role_404 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    client = _client()
    r = client.post(
        "/v1/rbac/assignments",
        params={"tenant_id": "t1", "user_id": "u", "role_id": "nope"},
    )
    assert r.status_code == 404


def test_authorize_endpoint() -> None:
    """验证 authorize_endpoint 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    client = _client()
    role = client.post("/v1/rbac/roles", params={"tenant_id": "t1", "name": "support_admin"}).json()
    role_id = role["role_id"]
    client.post(
        f"/v1/rbac/roles/{role_id}/permissions",
        params={"tenant_id": "t1"},
        json={"permissions": ["ticket.writeback", "ticket.read"]},
    )
    client.post(
        "/v1/rbac/assignments",
        params={"tenant_id": "t1", "user_id": "user-1", "role_id": role_id},
    )

    decision = client.post(
        "/v1/rbac/authorize",
        params={"tenant_id": "t1", "principal": "user-1", "action": "ticket.writeback"},
        json={"resource_type": "ticket", "resource_id": "tk-1"},
    ).json()
    # 验证审批边界，确保高风险动作必须经过审批。
    assert decision["outcome"] == "requires_approval"

    view = client.post(
        "/v1/rbac/authorize",
        params={"tenant_id": "t1", "principal": "user-1", "action": "ticket.view"},
        json={},
    ).json()
    assert view["outcome"] == "allowed"
