"""AgentForge 平台测试层：test_connector_api。

本测试模块验证 test_connector_api 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_list_connectors_empty、test_get_connector_404、test_connector_health_404、test_invoke_connector_not_registered_404。
"""

import uuid

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.application.connector_registry import ConnectorRegistry
from agentforge.platform.application.openapi_adapter import OpenAPIAdapter
from agentforge.platform.domain.connector import ConnectorSpec


def _seed_registry() -> ConnectorRegistry:
    """执行 _seed_registry 对应的逻辑，并返回处理结果。

    Returns:
        ConnectorRegistry，函数执行后的结果。
    """
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
    """执行 _make_client 对应的逻辑，并返回处理结果。

    Returns:
        TestClient，函数执行后的结果。
    """
    return TestClient(create_platform_app())


def test_list_connectors_empty() -> None:
    """验证 list_connectors_empty 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    client = _make_client()
    resp = client.get("/v1/connectors")
    assert resp.status_code == 200
    assert "connectors" in resp.json()


def test_get_connector_404() -> None:
    """验证 get_connector_404 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    client = _make_client()
    resp = client.get("/v1/connectors/does-not-exist")
    assert resp.status_code == 404


def test_connector_health_404() -> None:
    """验证 connector_health_404 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    client = _make_client()
    resp = client.get("/v1/connectors/does-not-exist/health")
    assert resp.status_code == 404


def test_invoke_connector_not_registered_404() -> None:
    """验证 invoke_connector_not_registered_404 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    client = _make_client()
    resp = client.post(
        "/v1/connectors/nope/invoke?action=ping&tenant_id=t1",
        json={},
    )
    assert resp.status_code == 404
