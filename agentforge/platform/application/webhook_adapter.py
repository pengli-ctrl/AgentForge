from __future__ import annotations

import hashlib
import hmac
from typing import Any

from agentforge.platform.domain.connector import WebhookDelivery


class WebhookSignatureVerifier:
    """Generic HMAC-SHA256 request signature verifier.

    Supports a per-tenant shared secret lookup. Signatures are computed over
    timestamp + nonce + raw body, mirroring the existing Feishu verifier but as
    a reusable provider-agnostic primitive (SC-301 "generic signed webhook").
    """

    def __init__(
        self,
        secret_provider: Any | None = None,
        default_secret: str | None = None,
    ) -> None:
        # secret_provider: callable(tenant_id) -> shared secret str | None
        self._secret_provider = secret_provider
        self._default_secret = default_secret

    def _secret_for(self, tenant_id: str) -> str | None:
        if self._secret_provider is not None:
            bound = getattr(self._secret_provider, "get_secret", None)
            if callable(bound):
                return bound(tenant_id)
            return self._secret_provider(tenant_id)
        return self._default_secret

    def verify(
        self,
        tenant_id: str,
        timestamp: str,
        nonce: str,
        body: bytes,
        signature: str,
    ) -> bool:
        secret = self._secret_for(tenant_id)
        if not secret:
            return False
        if not all((timestamp, nonce, signature)):
            return False
        payload = timestamp + nonce + body.decode("utf-8", errors="replace")
        expected = hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


class WebhookAdapter:
    """Normalizes a raw provider webhook payload into a WebhookDelivery.

    Subclasses override parse to map a specific provider's envelope (Feishu,
    generic JSON, form field, etc.) onto the standardized delivery. The
    signature verification itself is handled by WebhookSignatureVerifier at the
    router layer; this adapter is concerned with envelope -> delivery mapping.
    """

    def __init__(
        self,
        source: str,
        parse_factory: Any | None = None,
    ) -> None:
        self._source = source
        # parse_factory: callable(payload: dict) -> dict of delivery fields
        self._parse_factory = parse_factory

    def parse(
        self,
        tenant_id: str,
        payload: dict[str, Any],
        *,
        event_id: str = "",
        text: str = "",
        conversation_id: str = "",
        customer_id: str = "",
        source: str | None = None,
    ) -> WebhookDelivery:
        if self._parse_factory is not None:
            mapped = self._parse_factory(payload)
            event_id = event_id or str(mapped.get("event_id", ""))
            text = text or str(mapped.get("text", ""))
            conversation_id = conversation_id or str(mapped.get("conversation_id", ""))
            customer_id = customer_id or str(mapped.get("customer_id", ""))
        return WebhookDelivery(
            tenant_id=tenant_id,
            source=source or self._source,
            event_id=event_id,
            text=text,
            conversation_id=conversation_id,
            customer_id=customer_id,
            payload=payload,
        )


def generic_text_parser(payload: dict[str, Any]) -> dict[str, Any]:
    """Default parser for generic providers with a 'text' and optional ids."""
    return {
        "event_id": payload.get("event_id", ""),
        "text": payload.get("text", ""),
        "conversation_id": payload.get("conversation_id", ""),
        "customer_id": payload.get("customer_id", ""),
    }
