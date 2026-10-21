"""连接器API测试模块。

本测试模块验证 test_connector_api 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_list_connectors_empty、test_get_connector_404、test_connector_health_404、test_invoke_con
    nector_not_registered_404。
"""

import uuid

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.application.connector_registry import ConnectorRegistry
from agentforge.platform.application.openapi_adapter import OpenAPIAdapter
from agentforge.platform.domain.connector import ConnectorSpec


def _seed_registry() -> ConnectorRegistry:
    """初始化注册表。

    Returns:
        连接器注册表结果。
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
    """构造客户端。

    Returns:
        测试客户端结果。
    """
    return TestClient(create_platform_app())


def test_list_connectors_empty() -> None:
    """验证查询连接器空对应的测试场景。"""
    client = _make_client()
    resp = client.get("/v1/connectors")
    assert resp.status_code == 200
    assert "connectors" in resp.json()


def test_get_connector_404() -> None:
    """验证获取连接器资源不存在对应的测试场景。"""
    client = _make_client()
    resp = client.get("/v1/connectors/does-not-exist")
    assert resp.status_code == 404


def test_connector_health_404() -> None:
    """验证连接器健康资源不存在对应的测试场景。"""
    client = _make_client()
    resp = client.get("/v1/connectors/does-not-exist/health")
    assert resp.status_code == 404


def test_invoke_connector_not_registered_404() -> None:
    """验证调用连接器不已注册资源不存在对应的测试场景。"""
    client = _make_client()
    resp = client.post(
        "/v1/connectors/nope/invoke?action=ping&tenant_id=t1",
        json={},
    )
    assert resp.status_code == 404
