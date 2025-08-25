import uuid

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.application.connector_registry import ConnectorRegistry
from agentforge.platform.application.openapi_adapter import OpenAPIAdapter
from agentforge.platform.domain.connector import ConnectorSpec


def _seed_registry() -> ConnectorRegistry:
    registry = ConnectorRegistry()
    adapter = OpenAPIAdapter(
        "https://crm.test",
        request_fn=lambda m, u, **kw: {"ok": 1},
        audit_sink=None,
    )
    spec = ConnectorSpec(
        connector_id=f"conn-{uuid.uuid4().hex[:8]}",
        tenant_id="t1",
        name="openapi",
        kind="openapi",
        endpoint="https://crm.test",
        allowed_actions=["ping"],
    )
    registry.register(spec, adapter)
    return registry


def _make_client() -> TestClient:
    return TestClient(create_platform_app())


def test_list_connectors_empty() -> None:
    client = _make_client()
    resp = client.get("/v1/connectors")
    assert resp.status_code == 200
    assert "connectors" in resp.json()


def test_get_connector_404() -> None:
    client = _make_client()
    resp = client.get("/v1/connectors/does-not-exist")
    assert resp.status_code == 404


def test_connector_health_404() -> None:
    client = _make_client()
    resp = client.get("/v1/connectors/does-not-exist/health")
    assert resp.status_code == 404


def test_invoke_connector_not_registered_404() -> None:
    client = _make_client()
    resp = client.post(
        "/v1/connectors/nope/invoke?action=ping&tenant_id=t1",
        json={},
    )
    assert resp.status_code == 404
