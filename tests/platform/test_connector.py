"""连接器测试模块。

本测试模块验证 test_connector 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_webhook_signature_verifier_valid、test_webhook_signature_verifier_invalid、test_webhook_
    signature_verifier_missing_secret、test_webhook_signature_verifier_provider、test_webhook_adap
    ter_generic_parser、test_webhook_adapter_to_ticket_event、test_registry_register_and_adapter_c
    ontract、test_registry_tenant_isolation_on_invoke。
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
    """处理规格。

    Args:
        overrides: 配置覆盖项。

    Returns:
        连接器规格结果。
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
    """处理上下文。

    Args:
        overrides: 配置覆盖项。

    Returns:
        连接器上下文结果。
    """
    base: dict = {
        "tenant_id": "t1",
        "task_id": "task-1",
        "idempotency_key": "idem-1",
        "trace_id": "trace-1",
    }
    base.update(overrides)
    return ConnectorContext(**base)


def test_webhook_signature_verifier_valid() -> None:
    """验证Webhook签名核验器有效对应的测试场景。"""
    verifier = WebhookSignatureVerifier(default_secret="s3cret")
    body = b'{"event_id":"e1","text":"hello"}'
    import hashlib
    import hmac

    payload = "123" + "n1" + body.decode("utf-8")
    sig = hmac.new(b"s3cret", payload.encode("utf-8"), hashlib.sha256).hexdigest()
    assert verifier.verify("t1", "123", "n1", body, sig) is True


def test_webhook_signature_verifier_invalid() -> None:
    """验证Webhook签名核验器无效对应的测试场景。"""
    verifier = WebhookSignatureVerifier(default_secret="s3cret")
    assert verifier.verify("t1", "123", "n1", b'{"x":1}', "deadbeef") is False


def test_webhook_signature_verifier_missing_secret() -> None:
    """验证Webhook签名核验器缺失密钥对应的测试场景。"""
    verifier = WebhookSignatureVerifier(default_secret=None)
    assert verifier.verify("t1", "123", "n1", b"{1}", "sig") is False


def test_webhook_signature_verifier_provider() -> None:
    """验证Webhook签名核验器提供方对应的测试场景。"""

    class Provider:
        """可替换的密钥提供方。"""

        def get_secret(self, tenant_id: str) -> str | None:
            """获取密钥。

            Args:
                tenant_id: 租户 ID，用于数据隔离。

            Returns:
                无结果。
            """
            return "p" if tenant_id == "t1" else None

    verifier = WebhookSignatureVerifier(secret_provider=Provider())
    assert verifier._secret_for("t1") == "p"
    assert verifier._secret_for("t2") is None


def test_webhook_adapter_generic_parser() -> None:
    """验证Webhook适配器通用解析器对应的测试场景。"""
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
    """验证Webhook适配器到工单事件对应的测试场景。"""
    adapter = WebhookAdapter("openapi")
    delivery = adapter.parse("t1", {"reply_target": "rt-1"}, event_id="e2", text="x")
    ev = delivery.to_ticket_event()
    assert ev["tenant_id"] == "t1"
    assert ev["source"] == "openapi"
    assert ev["message_id"] == "e2"
    assert ev["reply_target"] == "rt-1"


@pytest.mark.asyncio
async def test_registry_register_and_adapter_contract() -> None:
    """验证注册表注册及适配器契约对应的测试场景。"""
    calls: list[dict] = []

    async def request_fn(method: str, url: str, **kwargs) -> dict:
        """处理请求函数。

        Args:
            method: HTTP 或业务方法名。
            url: 目标 URL。
            kwargs: 关键字参数。

        Returns:
            结构化结果字典。
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
    assert calls[0]["h"]["X-Idempotency-Key"] == "idem-1"
    assert calls[0]["url"] == "https://crm.test/tickets"


@pytest.mark.asyncio
async def test_registry_tenant_isolation_on_invoke() -> None:
    """验证注册表租户隔离时调用对应的测试场景。"""
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


@pytest.mark.asyncio
async def test_registry_tenant_isolation_on_compensate() -> None:
    """验证注册表租户隔离时补偿对应的测试场景。"""
    adapter = OpenAPIAdapter("https://crm.test", audit_sink=None)
    spec = _spec(tenant_id="t1", allowed_actions=["ledger.compensate"])
    registry = ConnectorRegistry()
    registry.register(spec, adapter)

    result = await registry.compensate(
        spec.connector_id,
        "ledger.compensate",
        {},
        _context(tenant_id="t2"),
    )

    assert result.ok is False
    assert "tenant mismatch" in (result.error or "")
    assert "tenant" in (result.error or "")


@pytest.mark.asyncio
async def test_registry_action_not_allowed() -> None:
    """验证注册表操作不允许对应的测试场景。"""
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
    """验证注册表停用及未注册对应的测试场景。"""
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
    """验证注册表健康及查询对应的测试场景。"""
    adapter = OpenAPIAdapter("https://x.test", audit_sink=None)
    registry = ConnectorRegistry()
    spec = _spec()
    registry.register(spec, adapter)
    health = await registry.health(spec.connector_id)
    assert health is not None
    assert health.healthy is True
    assert len(await registry.list_health("t1")) >= 1


@pytest.mark.asyncio
async def test_openapi_adapter_retry_on_failure() -> None:
    """验证OpenAPI适配器重试时失败对应的测试场景。"""
    attempts = {"n": 0}

    async def fail_once(method: str, url: str, **kwargs) -> dict:
        """处理失败一次。

        Args:
            method: HTTP 或业务方法名。
            url: 目标 URL。
            kwargs: 关键字参数。

        Returns:
            结构化结果字典。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
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
    """验证OpenAPI适配器审计接收器对应的测试场景。"""
    audited: list[dict] = []

    async def sink(record: dict) -> None:
        """处理接收器。

        Args:
            record: 待处理的领域记录。
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
    """验证凭据参考密钥对应的测试场景。"""
    ref = CredentialReference(ref="vault://crm/token", vault="default")
    assert ref.ref.startswith("vault://")
    assert "secret" not in ref.model_dump()
