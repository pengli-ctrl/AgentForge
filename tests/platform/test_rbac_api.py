from __future__ import annotations

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.runtime import build_memory_container


def _client() -> TestClient:
    container = build_memory_container()
    app = create_platform_app(container)
    return TestClient(app)


def test_create_role_and_list() -> None:
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
    client = _client()
    r = client.post(
        "/v1/rbac/assignments",
        params={"tenant_id": "t1", "user_id": "u", "role_id": "nope"},
    )
    assert r.status_code == 404


def test_authorize_endpoint() -> None:
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
    # writeback is high-risk -> requires approval even when authorized
    assert decision["outcome"] == "requires_approval"

    view = client.post(
        "/v1/rbac/authorize",
        params={"tenant_id": "t1", "principal": "user-1", "action": "ticket.view"},
        json={},
    ).json()
    assert view["outcome"] == "allowed"
