from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConnectorKind(str, Enum):
    """Connector types supported by the Connector SDK."""

    WEBHOOK = "webhook"
    OPENAPI = "openapi"
    HTTP = "http"


class ConnectorRiskLevel(str, Enum):
    """Risk classification of a write/read connector action."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CredentialReference(BaseModel):
    """Reference to a stored credential; never holds the secret itself.

    Secrets are kept in a secret store (e.g. vault) and only the reference
    key is persisted / logged. This aligns with the "credentials by reference"
    requirement (SC-303).
    """

    model_config = ConfigDict(extra="forbid")

    ref: str
    vault: str = "default"
    hint: str | None = None


class ConnectorContext(BaseModel):
    """Caller context passed into every connector invocation."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    task_id: str = ""
    idempotency_key: str = ""
    trace_id: str = ""
    actor: str = "system"


class ConnectorSpec(BaseModel):
    """Immutable registration record for a connector instance."""

    model_config = ConfigDict(extra="forbid")

    connector_id: str
    tenant_id: str
    name: str
    kind: ConnectorKind
    version: str = "1.0"
    risk_level: ConnectorRiskLevel = ConnectorRiskLevel.LOW
    endpoint: str | None = None
    allowed_actions: list[str] = Field(default_factory=list)
    credential: CredentialReference | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConnectorHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector_id: str
    healthy: bool
    detail: str = ""


class ConnectorInvocationResult(BaseModel):
    """Result of a connector invoke/compensate call."""

    model_config = ConfigDict(extra="forbid")

    connector_id: str
    action: str
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    idempotent_replay: bool = False


class WebhookDelivery(BaseModel):
    """Normalized inbound event produced by a Webhook Adapter."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    source: str
    event_type: str = "message"
    event_id: str = ""
    conversation_id: str = ""
    customer_id: str = ""
    text: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_ticket_event(self) -> dict[str, Any]:
        """Convert into the ingress shape expected by SupportTicketService."""
        return {
            "tenant_id": self.tenant_id,
            "source": self.source,
            "message_id": self.event_id,
            "conversation_id": self.conversation_id,
            "customer_id": self.customer_id,
            "text": self.text,
            "reply_target": self.payload.get("reply_target"),
        }


_SENSITIVE_KEY_TOKENS = (
    "secret",
    "password",
    "authorization",
    "api-key",
    "api_key",
    "apikey",
    "auth_value",
    "access_token",
    "refresh_token",
    "client_secret",
    "token",
)


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return any(tok in lower for tok in _SENSITIVE_KEY_TOKENS)


def _redact(value: Any, key: str = "") -> Any:
    """Recursively mask values that sit under a secret-looking key."""
    if _is_sensitive_key(key):
        # Preserve presence but never echo the plaintext value.
        return "***" if value else value
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item, key) for item in value]
    return value


def spec_to_public_dict(spec: ConnectorSpec) -> dict[str, Any]:
    """Serialise a ConnectorSpec for external API responses with credentials redacted.

    Secret material such as ``config["auth_value"]`` (and any secret-looking
    header value, e.g. an ``Authorization`` bearer token) is replaced with a
    ``***`` marker so list/detail/register responses never echo plaintext
    credentials. A ``credentials_configured`` boolean signals presence without
    exposing the value.
    """
    data = spec.model_dump(mode="json")
    data["config"] = _redact(spec.config or {})
    data["credentials_configured"] = bool(spec.config and spec.config.get("auth_value"))
    return data
