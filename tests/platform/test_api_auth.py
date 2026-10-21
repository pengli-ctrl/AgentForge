"""API鉴权测试模块。

本测试模块验证 test_api_auth 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：build_authenticated_client、test_tenant_api_key_is_required_and_scoped、test_admin_key_can_ma
    nage_outbox_but_tenant_key_cannot、base_settings、test_default_settings_require_auth、test_dev_
    without_keys_falls_back_to_disabled、test_prod_without_keys_refuses_startup、test_prod_with_ke
    ys_enables_auth。
"""

from fastapi.testclient import TestClient

from agentforge.platform.api.app import _resolve_auth_enabled, create_platform_app
from agentforge.platform.api.security import ApiKeyAuthenticator
from agentforge.platform.runtime import build_memory_container
from agentforge.platform.settings import Settings


def build_authenticated_client() -> TestClient:
    """构建客户端。

    Returns:
        测试客户端结果。
    """
    authenticator = ApiKeyAuthenticator(
        enabled=True,
        tenant_keys={"tenant-key-1": "tenant-1"},
        admin_key="admin-key",
    )
    container = build_memory_container(authenticator=authenticator)
    return TestClient(create_platform_app(container))


def test_tenant_api_key_is_required_and_scoped() -> None:
    """验证租户API键是否必需及按范围隔离对应的测试场景。"""
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
    """验证管理键可以Outbox租户键无法对应的测试场景。"""
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


# --- P0-1 安全默认值反转：fail-closed 推导 ---


def base_settings(**overrides) -> Settings:
    """处理基础配置。

    Args:
        overrides: 配置覆盖项。

    Returns:
        配置结果。
    """
    values = dict(
        env="dev",
        api_keys={},
        admin_api_key="",
        auth_enabled=True,
    )
    values.update(overrides)
    return Settings(**values)


def test_default_settings_require_auth(monkeypatch) -> None:
    """验证默认配置要求鉴权对应的测试场景。

    Args:
        monkeypatch: pytest 提供的猴子补丁对象。
    """
    s = base_settings()
    assert s.auth_enabled is True


def test_dev_without_keys_falls_back_to_disabled() -> None:
    """验证不包含键回退返回到停用对应的测试场景。"""
    s = base_settings(env="dev")
    assert _resolve_auth_enabled(s) is False


def test_prod_without_keys_refuses_startup() -> None:
    """验证生产不包含键对应的测试场景。

    Raises:
        AssertionError: 操作无法完成时抛出。
    """
    s = base_settings(env="prod")
    try:
        _resolve_auth_enabled(s)
    except RuntimeError as e:
        assert "authentication is enabled" in str(e).lower()
    else:
        raise AssertionError("expected RuntimeError")


def test_prod_with_keys_enables_auth() -> None:
    """验证生产使用键鉴权对应的测试场景。"""
    s = base_settings(env="prod", api_keys={"k": "t1"})
    assert _resolve_auth_enabled(s) is True


def test_prod_no_keys_allow_no_auth_env_opens(monkeypatch) -> None:
    """验证生产无键允许无鉴权环境对应的测试场景。

    Args:
        monkeypatch: pytest 提供的猴子补丁对象。
    """
    monkeypatch.setenv("AGENTFORGE_ALLOW_NO_AUTH", "true")
    s = base_settings(env="prod")
    assert _resolve_auth_enabled(s) is False


def test_explicit_auth_enabled_false_turns_off_even_with_keys() -> None:
    """验证鉴权启用假使用键对应的测试场景。"""
    s = base_settings(env="prod", api_keys={"k": "t1"}, auth_enabled=False)
    assert _resolve_auth_enabled(s) is False
