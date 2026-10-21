"""连接器模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConnectorKind(str, Enum):
    """连接器种类枚举。"""

    WEBHOOK = "webhook"
    OPENAPI = "openapi"
    HTTP = "http"


class ConnectorRiskLevel(str, Enum):
    """风险级别枚举。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CredentialReference(BaseModel):
    """凭据参考相关组件。

    Attributes:
        ref: 引用。
        vault: 密钥库。
        hint: 字段值。
    """

    model_config = ConfigDict(extra="forbid")

    ref: str
    vault: str = "default"
    hint: str | None = None


class ConnectorContext(BaseModel):
    """上下文领域组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        task_id: 任务ID。
        idempotency_key: 幂等键，用于避免重复处理。
        trace_id: 链路ID。
        actor: 参与者。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    task_id: str = ""
    idempotency_key: str = ""
    trace_id: str = ""
    actor: str = "system"


class ConnectorSpec(BaseModel):
    """规格相关组件。

    Attributes:
        connector_id: 连接器ID。
        tenant_id: 租户 ID，用于数据隔离。
        name: 名称。
        kind: 资源种类。
        version: 版本号。
        risk_level: 风险级别。
        endpoint: 端点。
        allowed_actions: 允许操作。
        credential: 凭据。
        config: 组件配置。
        enabled: 是否启用。
        created_at: 创建时间。
    """

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
    """健康相关组件。

    Attributes:
        connector_id: 连接器ID。
        healthy: 字段值。
        detail: 详情。
    """

    model_config = ConfigDict(extra="forbid")

    connector_id: str
    healthy: bool
    detail: str = ""


class ConnectorInvocationResult(BaseModel):
    """结果相关组件。

    Attributes:
        connector_id: 连接器ID。
        action: 操作。
        ok: 字段值。
        data: 数据内容。
        error: 错误信息。
        idempotent_replay: 幂等。
    """

    model_config = ConfigDict(extra="forbid")

    connector_id: str
    action: str
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    idempotent_replay: bool = False


class WebhookDelivery(BaseModel):
    """Webhook相关组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        source: 调用或事件来源。
        event_type: 事件。
        event_id: 事件 ID。
        conversation_id: 会话ID。
        customer_id: 客户ID。
        text: 文本。
        payload: 事件、工作流或请求载荷。
        received_at: 于。
    """

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
        """将 Connector 执行结果转换为工单事件载荷。

        Returns:
            结构化结果字典。
        """
        return {
            "tenant_id": self.tenant_id,
            "source": self.source,
            "message_id": self.event_id,
            "conversation_id": self.conversation_id,
            "customer_id": self.customer_id,
            "text": self.text,
            "reply_target": self.payload.get("reply_target"),
        }


# 常量：_SENSITIVE_KEY_TOKENS。
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
    """判断键是否成立。

    Args:
        key: 缓存或配置键。

    Returns:
        操作是否成功。
    """
    lower = key.lower()
    return any(tok in lower for tok in _SENSITIVE_KEY_TOKENS)


def _redact(value: Any, key: str = "") -> Any:
    """脱敏数据。

    Args:
        value: 待处理值。
        key: 缓存或配置键。

    Returns:
        处理结果对象。
    """
    if _is_sensitive_key(key):
        return "***" if value else value
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item, key) for item in value]
    return value


def spec_to_public_dict(spec: ConnectorSpec) -> dict[str, Any]:
    """处理规格到公共字典。

    Args:
        spec: 资源规格定义。

    Returns:
        结构化结果字典。
    """
    data = spec.model_dump(mode="json")
    data["config"] = _redact(spec.config or {})
    data["credentials_configured"] = bool(spec.config and spec.config.get("auth_value"))
    return data
