from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.api.security import ApiKeyAuthenticator
from agentforge.platform.runtime import build_memory_container


def build_authenticated_client() -> TestClient:
    authenticator = ApiKeyAuthenticator(
        enabled=True,
        tenant_keys={"tenant-key-1": "tenant-1"},
        admin_key="admin-key",
    )
    container = build_memory_container(authenticator=authenticator)
    return TestClient(create_platform_app(container))


def test_tenant_api_key_is_required_and_scoped() -> None:
    client = build_authenticated_client()
    event = {
        "tenant_id": "tenant-1",
        "source": "feishu",
        "message_id": "auth-msg-1",
        "text": "How do I use this product?",
    }

    assert client.post("/v1/events/im", json=event).status_code == 401
    assert (
        client.post("/v1/events/im", json=event, headers={"X-API-Key": "bad-key"}).status_code
        == 401
    )

    wrong_tenant = dict(event, tenant_id="tenant-2")
    assert (
        client.post(
            "/v1/events/im",
            json=wrong_tenant,
            headers={"X-API-Key": "tenant-key-1"},
        ).status_code
        == 403
    )

    response = client.post(
        "/v1/events/im",
        json=event,
        headers={"X-API-Key": "tenant-key-1"},
    )
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "tenant-1"


def test_admin_key_can_manage_outbox_but_tenant_key_cannot() -> None:
    client = build_authenticated_client()

    assert client.get("/v1/outbox/failed").status_code == 401
    assert (
        client.get(
            "/v1/outbox/failed",
            headers={"X-API-Key": "tenant-key-1"},
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/v1/outbox/failed",
            headers={"X-API-Key": "admin-key"},
        ).status_code
        == 200
    )
