"""AgentForge 平台测试层：test_api_auth。

本测试模块验证 test_api_auth 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：build_authenticated_client、test_tenant_api_key_is_required_and_scoped、test_admin_key_can_manage_outbox_but_tenant_key_cannot、base_settings、test_default_settings_require_auth、test_dev_without_keys_falls_back_to_disabled、test_prod_without_keys_refuses_startup、test_prod_with_keys_enables_auth。
"""

from fastapi.testclient import TestClient

from agentforge.platform.api.app import _resolve_auth_enabled, create_platform_app
from agentforge.platform.api.security import ApiKeyAuthenticator
from agentforge.platform.runtime import build_memory_container
from agentforge.platform.settings import Settings


def build_authenticated_client() -> TestClient:
    """构建目标对象，并返回调用方需要的结果。

    Returns:
        TestClient，函数执行后的结果。
    """
    authenticator = ApiKeyAuthenticator(
        enabled=True,
        tenant_keys={"tenant-key-1": "tenant-1"},
        admin_key="admin-key",
    )
    container = build_memory_container(authenticator=authenticator)
    return TestClient(create_platform_app(container))


def test_tenant_api_key_is_required_and_scoped() -> None:
    """验证 tenant_api_key_is_required_and_scoped 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
    """验证 admin_key_can_manage_outbox_but_tenant_key_cannot 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
    """执行 base_settings 对应的逻辑，并返回处理结果。

    Args:
        **overrides: Any，调用方传入的 **overrides 参数。

    Returns:
        Settings，函数执行后的结果。
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
    """验证 default_settings_require_auth 对应的业务行为、边界条件和回归场景。

    Args:
        monkeypatch: Any，调用方传入的 monkeypatch 参数。

    Returns:
        None，函数执行后的结果。
    """
    s = base_settings()
    assert s.auth_enabled is True


def test_dev_without_keys_falls_back_to_disabled() -> None:
    """验证 dev_without_keys_falls_back_to_disabled 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    s = base_settings(env="dev")
    assert _resolve_auth_enabled(s) is False


def test_prod_without_keys_refuses_startup() -> None:
    """验证 prod_without_keys_refuses_startup 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。

    Raises:
        AssertionError: 当输入、状态或外部依赖不满足要求时抛出。
    """
    s = base_settings(env="prod")
    try:
        _resolve_auth_enabled(s)
    except RuntimeError as e:
        assert "authentication is enabled" in str(e).lower()
    else:
        raise AssertionError("expected RuntimeError")


def test_prod_with_keys_enables_auth() -> None:
    """验证 prod_with_keys_enables_auth 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    s = base_settings(env="prod", api_keys={"k": "t1"})
    assert _resolve_auth_enabled(s) is True


def test_prod_no_keys_allow_no_auth_env_opens(monkeypatch) -> None:
    """验证 prod_no_keys_allow_no_auth_env_opens 对应的业务行为、边界条件和回归场景。

    Args:
        monkeypatch: Any，调用方传入的 monkeypatch 参数。

    Returns:
        None，函数执行后的结果。
    """
    monkeypatch.setenv("AGENTFORGE_ALLOW_NO_AUTH", "true")
    s = base_settings(env="prod")
    assert _resolve_auth_enabled(s) is False


def test_explicit_auth_enabled_false_turns_off_even_with_keys() -> None:
    """验证 explicit_auth_enabled_false_turns_off_even_with_keys 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    s = base_settings(env="prod", api_keys={"k": "t1"}, auth_enabled=False)
    assert _resolve_auth_enabled(s) is False
