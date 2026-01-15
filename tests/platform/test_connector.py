"""AgentForge 平台测试层：test_connector。

本测试模块验证 test_connector 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_webhook_signature_verifier_valid、test_webhook_signature_verifier_invalid、test_webhook_signature_verifier_missing_secret、test_webhook_signature_verifier_provider、test_webhook_adapter_generic_parser、test_webhook_adapter_to_ticket_event、test_registry_register_and_adapter_contract、test_registry_tenant_isolation_on_invoke。
"""

import uuid

import pytest

from agentforge.platform.application.connector_registry import ConnectorRegistry
from agentforge.platform.application.openapi_adapter import OpenAPIAdapter
from agentforge.platform.application.webhook_adapter import (
    WebhookAdapter,
    WebhookSignatureVerifier,
    generic_text_parser,
)
from agentforge.platform.domain.connector import (
    ConnectorContext,
    ConnectorInvocationResult,
    ConnectorSpec,
    CredentialReference,
)


def _spec(**overrides) -> ConnectorSpec:
    """执行 _spec 对应的逻辑，并返回处理结果。

    Args:
        **overrides: Any，调用方传入的 **overrides 参数。

    Returns:
        ConnectorSpec，函数执行后的结果。
    """
    base: dict = {
        "connector_id": f"conn-{uuid.uuid4().hex[:8]}",
        "tenant_id": "t1",
        "name": "openapi",
        "kind": "openapi",
        "endpoint": "https://example.test",
        "allowed_actions": ["publish_review", "create_ticket"],
    }
    base.update(overrides)
    return ConnectorSpec(**base)


def _context(**overrides) -> ConnectorContext:
    """执行 _context 对应的逻辑，并返回处理结果。

    Args:
        **overrides: Any，调用方传入的 **overrides 参数。

    Returns:
        ConnectorContext，函数执行后的结果。
    """
    base: dict = {
        "tenant_id": "t1",
        "task_id": "task-1",
        "idempotency_key": "idem-1",
        "trace_id": "trace-1",
    }
    base.update(overrides)
    return ConnectorContext(**base)


# 说明：该步骤用于保证业务流程、租户隔离和可追踪性。


def test_webhook_signature_verifier_valid() -> None:
    """验证 webhook_signature_verifier_valid 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    verifier = WebhookSignatureVerifier(default_secret="s3cret")
    body = b'{"event_id":"e1","text":"hello"}'
    import hashlib
    import hmac

    payload = "123" + "n1" + body.decode("utf-8")
    sig = hmac.new(b"s3cret", payload.encode("utf-8"), hashlib.sha256).hexdigest()
    assert verifier.verify("t1", "123", "n1", body, sig) is True


def test_webhook_signature_verifier_invalid() -> None:
    """验证 webhook_signature_verifier_invalid 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    verifier = WebhookSignatureVerifier(default_secret="s3cret")
    assert verifier.verify("t1", "123", "n1", b'{"x":1}', "deadbeef") is False


def test_webhook_signature_verifier_missing_secret() -> None:
    """验证 webhook_signature_verifier_missing_secret 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    verifier = WebhookSignatureVerifier(default_secret=None)
    assert verifier.verify("t1", "123", "n1", b"{1}", "sig") is False


def test_webhook_signature_verifier_provider() -> None:
    """验证 webhook_signature_verifier_provider 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """

    class Provider:
        """Provider。

        Provider 封装相关领域行为，保持职责单一并降低调用方复杂度。

        主要成员：
        - 方法 get_secret()。

        设计约束：
        - 保持接口稳定，不向调用方暴露不必要的数据结构。
        - 涉及租户、权限、审计或成本的逻辑必须显式处理。
        """

        def get_secret(self, tenant_id: str) -> str | None:
            """读取并返回指定数据，并返回调用方需要的结果。

            Args:
                tenant_id: str，调用方传入的 tenant_id 参数。

            Returns:
                str | None，函数执行后的结果。
            """
            return "p" if tenant_id == "t1" else None

    verifier = WebhookSignatureVerifier(secret_provider=Provider())
    assert verifier._secret_for("t1") == "p"
    assert verifier._secret_for("t2") is None


# 说明：该步骤用于保证业务流程、租户隔离和可追踪性。


def test_webhook_adapter_generic_parser() -> None:
    """验证 webhook_adapter_generic_parser 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    adapter = WebhookAdapter("generic", parse_factory=generic_text_parser)
    delivery = adapter.parse(
        "t1",
        {"event_id": "e1", "text": "hi", "conversation_id": "c1", "customer_id": "u1"},
    )
    assert delivery.source == "generic"
    assert delivery.event_id == "e1"
    assert delivery.text == "hi"
    assert delivery.conversation_id == "c1"
    assert delivery.customer_id == "u1"


def test_webhook_adapter_to_ticket_event() -> None:
    """验证 webhook_adapter_to_ticket_event 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    adapter = WebhookAdapter("openapi")
    delivery = adapter.parse("t1", {"reply_target": "rt-1"}, event_id="e2", text="x")
    ev = delivery.to_ticket_event()
    assert ev["tenant_id"] == "t1"
    assert ev["source"] == "openapi"
    assert ev["message_id"] == "e2"
    assert ev["reply_target"] == "rt-1"


# 说明：该步骤用于保证业务流程、租户隔离和可追踪性。


@pytest.mark.asyncio
async def test_registry_register_and_adapter_contract() -> None:
    """验证 registry_register_and_adapter_contract 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    calls: list[dict] = []

    async def request_fn(method: str, url: str, **kwargs) -> dict:
        """执行 request_fn 对应的逻辑，并返回处理结果。

        Args:
            method: str，调用方传入的 method 参数。
            url: str，调用方传入的 url 参数。
            **kwargs: Any，调用方传入的 **kwargs 参数。

        Returns:
            dict，函数执行后的结果。
        """
        calls.append({"m": method, "url": url, "h": kwargs.get("headers", {})})
        return {"code": 0}

    adapter = OpenAPIAdapter(
        "https://crm.test",
        request_fn=request_fn,
        audit_sink=None,
    )
    spec = _spec()
    registry = ConnectorRegistry()
    registry.register(spec, adapter)

    result = await registry.invoke(
        spec.connector_id,
        "create_ticket",
        {"method": "POST", "path": "/tickets", "body": {"subject": "s"}},
        _context(),
    )
    assert isinstance(result, ConnectorInvocationResult)
    assert result.ok is True
    assert "code" in result.data
    # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
    assert calls[0]["h"]["X-Idempotency-Key"] == "idem-1"
    assert calls[0]["url"] == "https://crm.test/tickets"


@pytest.mark.asyncio
async def test_registry_tenant_isolation_on_invoke() -> None:
    """验证 registry_tenant_isolation_on_invoke 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    adapter = OpenAPIAdapter(
        "https://crm.test",
        request_fn=None,
        audit_sink=None,
    )
    spec = _spec(tenant_id="t1")
    registry = ConnectorRegistry()
    registry.register(spec, adapter)

    # 验证租户上下文和隔离约束。
    result = await registry.invoke(
        spec.connector_id,
        "create_ticket",
        {"method": "POST", "body": {}},
        _context(tenant_id="t2"),
    )
    assert result.ok is False
    assert "tenant" in (result.error or "")


@pytest.mark.asyncio
async def test_registry_action_not_allowed() -> None:
    """验证 registry_action_not_allowed 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    adapter = OpenAPIAdapter("https://crm.test", audit_sink=None)
    spec = _spec(allowed_actions=["publish_review"])
    registry = ConnectorRegistry()
    registry.register(spec, adapter)
    result = await registry.invoke(
        spec.connector_id,
        "create_ticket",
        {"method": "POST"},
        _context(),
    )
    assert result.ok is False
    assert "not allowed" in (result.error or "")


@pytest.mark.asyncio
async def test_registry_disabled_and_unregistered() -> None:
    """验证 registry_disabled_and_unregistered 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    registry = ConnectorRegistry()
    unreg = await registry.invoke("nope", "x", {}, _context())
    assert unreg.ok is False

    adapter = OpenAPIAdapter("https://crm.test", audit_sink=None)
    spec = _spec(enabled=False)
    registry.register(spec, adapter)
    disabled = await registry.invoke(spec.connector_id, "x", {}, _context())
    assert disabled.ok is False
    assert "disabled" in (disabled.error or "")


@pytest.mark.asyncio
async def test_registry_health_and_list() -> None:
    """验证 registry_health_and_list 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    adapter = OpenAPIAdapter("https://x.test", audit_sink=None)
    registry = ConnectorRegistry()
    # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
    spec = _spec()
    registry.register(spec, adapter)
    health = await registry.health(spec.connector_id)
    assert health is not None
    assert health.healthy is True
    assert len(await registry.list_health("t1")) >= 1


@pytest.mark.asyncio
async def test_openapi_adapter_retry_on_failure() -> None:
    """验证 openapi_adapter_retry_on_failure 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。

    Raises:
        RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
    """
    attempts = {"n": 0}

    async def fail_once(method: str, url: str, **kwargs) -> dict:
        """执行 fail_once 对应的逻辑，并返回处理结果。

        Args:
            method: str，调用方传入的 method 参数。
            url: str，调用方传入的 url 参数。
            **kwargs: Any，调用方传入的 **kwargs 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("boom")
        return {"ok": True}

    adapter = OpenAPIAdapter(
        "https://crm.test",
        request_fn=fail_once,
        max_retries=2,
        retry_backoff_seconds=0.0,
        audit_sink=None,
    )
    result = await adapter.invoke("retry", {"method": "GET", "path": "/x"}, _context())
    assert result.ok is True
    assert attempts["n"] == 2


@pytest.mark.asyncio
async def test_openapi_adapter_audit_sink() -> None:
    """验证 openapi_adapter_audit_sink 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    audited: list[dict] = []

    async def sink(record: dict) -> None:
        """执行 sink 对应的逻辑，并返回处理结果。

        Args:
            record: dict，调用方传入的 record 参数。

        Returns:
            None，函数执行后的结果。
        """
        audited.append(record)

    adapter = OpenAPIAdapter(
        "https://crm.test",
        request_fn=lambda m, u, **kw: {"ok": 1},
        audit_sink=sink,
    )
    await adapter.invoke("act", {"method": "GET", "path": "/"}, _context())
    assert len(audited) == 1
    assert audited[0]["idempotency_key"] == "idem-1"
    assert audited[0]["tenant_id"] == "t1"


def test_credential_reference_never_holds_secret() -> None:
    """验证 credential_reference_never_holds_secret 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    ref = CredentialReference(ref="vault://crm/token", vault="default")
    assert ref.ref.startswith("vault://")
    assert "secret" not in ref.model_dump()
