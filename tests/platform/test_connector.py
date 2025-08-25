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
    base: dict = {
        "tenant_id": "t1",
        "task_id": "task-1",
        "idempotency_key": "idem-1",
        "trace_id": "trace-1",
    }
    base.update(overrides)
    return ConnectorContext(**base)


# ---- WebhookSignatureVerifier ----


def test_webhook_signature_verifier_valid() -> None:
    verifier = WebhookSignatureVerifier(default_secret="s3cret")
    body = b'{"event_id":"e1","text":"hello"}'
    import hashlib
    import hmac

    payload = "123" + "n1" + body.decode("utf-8")
    sig = hmac.new(b"s3cret", payload.encode("utf-8"), hashlib.sha256).hexdigest()
    assert verifier.verify("t1", "123", "n1", body, sig) is True


def test_webhook_signature_verifier_invalid() -> None:
    verifier = WebhookSignatureVerifier(default_secret="s3cret")
    assert verifier.verify("t1", "123", "n1", b'{"x":1}', "deadbeef") is False


def test_webhook_signature_verifier_missing_secret() -> None:
    verifier = WebhookSignatureVerifier(default_secret=None)
    assert verifier.verify("t1", "123", "n1", b"{1}", "sig") is False


def test_webhook_signature_verifier_provider() -> None:
    class Provider:
        def get_secret(self, tenant_id: str) -> str | None:
            return "p" if tenant_id == "t1" else None

    verifier = WebhookSignatureVerifier(secret_provider=Provider())
    assert verifier._secret_for("t1") == "p"
    assert verifier._secret_for("t2") is None


# ---- WebhookAdapter ----


def test_webhook_adapter_generic_parser() -> None:
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
    adapter = WebhookAdapter("openapi")
    delivery = adapter.parse("t1", {"reply_target": "rt-1"}, event_id="e2", text="x")
    ev = delivery.to_ticket_event()
    assert ev["tenant_id"] == "t1"
    assert ev["source"] == "openapi"
    assert ev["message_id"] == "e2"
    assert ev["reply_target"] == "rt-1"


# ---- ConnectorRegistry + credential reference ----


@pytest.mark.asyncio
async def test_registry_register_and_adapter_contract() -> None:
    calls: list[dict] = []

    async def request_fn(method: str, url: str, **kwargs) -> dict:
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
    # idempotency header forwarded
    assert calls[0]["h"]["X-Idempotency-Key"] == "idem-1"
    assert calls[0]["url"] == "https://crm.test/tickets"


@pytest.mark.asyncio
async def test_registry_tenant_isolation_on_invoke() -> None:
    adapter = OpenAPIAdapter(
        "https://crm.test",
        request_fn=None,
        audit_sink=None,
    )
    spec = _spec(tenant_id="t1")
    registry = ConnectorRegistry()
    registry.register(spec, adapter)

    # cross-tenant invoke is rejected
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
    adapter = OpenAPIAdapter("https://x.test", audit_sink=None)
    registry = ConnectorRegistry()
    # adapter name must match spec name; use the actual connector_id
    spec = _spec()
    registry.register(spec, adapter)
    health = await registry.health(spec.connector_id)
    assert health is not None
    assert health.healthy is True
    assert len(await registry.list_health("t1")) >= 1


@pytest.mark.asyncio
async def test_openapi_adapter_retry_on_failure() -> None:
    attempts = {"n": 0}

    async def fail_once(method: str, url: str, **kwargs) -> dict:
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
    audited: list[dict] = []

    async def sink(record: dict) -> None:
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
    ref = CredentialReference(ref="vault://crm/token", vault="default")
    assert ref.ref.startswith("vault://")
    assert "secret" not in ref.model_dump()
