"""AgentForge 平台领域模型层：connector。

本模块定义 connector 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要类：ConnectorKind、ConnectorRiskLevel、CredentialReference、ConnectorContext、ConnectorSpec、ConnectorHealth、ConnectorInvocationResult、WebhookDelivery。
- 主要函数：spec_to_public_dict。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConnectorKind(str, Enum):
    """ConnectorKind。

    ConnectorKind 是状态或类型枚举，用于约束系统内部取值，避免使用散落的字符串常量。

    主要成员：
    - WEBHOOK: 'webhook'。
    - OPENAPI: 'openapi'。
    - HTTP: 'http'。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    WEBHOOK = "webhook"
    OPENAPI = "openapi"
    HTTP = "http"


class ConnectorRiskLevel(str, Enum):
    """ConnectorRiskLevel。

    ConnectorRiskLevel 是状态或类型枚举，用于约束系统内部取值，避免使用散落的字符串常量。

    主要成员：
    - LOW: 'low'。
    - MEDIUM: 'medium'。
    - HIGH: 'high'。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CredentialReference(BaseModel):
    """CredentialReference。

    CredentialReference 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - ref: str。
    - vault: str。
    - hint: str | None。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    ref: str
    vault: str = "default"
    hint: str | None = None


class ConnectorContext(BaseModel):
    """ConnectorContext。

    ConnectorContext 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - tenant_id: str。
    - task_id: str。
    - idempotency_key: str。
    - trace_id: str。
    - actor: str。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    task_id: str = ""
    idempotency_key: str = ""
    trace_id: str = ""
    actor: str = "system"


class ConnectorSpec(BaseModel):
    """ConnectorSpec。

    ConnectorSpec 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - connector_id: str。
    - tenant_id: str。
    - name: str。
    - kind: ConnectorKind。
    - version: str。
    - risk_level: ConnectorRiskLevel。
    - endpoint: str | None。
    - allowed_actions: list[str]。
    - credential: CredentialReference | None。
    - config: dict[str, Any]。
    - enabled: bool。
    - created_at: datetime。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
    """ConnectorHealth。

    ConnectorHealth 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - connector_id: str。
    - healthy: bool。
    - detail: str。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    connector_id: str
    healthy: bool
    detail: str = ""


class ConnectorInvocationResult(BaseModel):
    """ConnectorInvocationResult。

    ConnectorInvocationResult 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - connector_id: str。
    - action: str。
    - ok: bool。
    - data: dict[str, Any]。
    - error: str | None。
    - idempotent_replay: bool。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    connector_id: str
    action: str
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    idempotent_replay: bool = False


class WebhookDelivery(BaseModel):
    """WebhookDelivery。

    WebhookDelivery 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - tenant_id: str。
    - source: str。
    - event_type: str。
    - event_id: str。
    - conversation_id: str。
    - customer_id: str。
    - text: str。
    - payload: dict[str, Any]。
    - received_at: datetime。
    - 方法 to_ticket_event()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
        """执行 to_ticket_event 对应的逻辑，并返回处理结果。

        Returns:
            dict[str, Any]，函数执行后的结果。
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
    """执行 _is_sensitive_key 对应的逻辑，并返回处理结果。

    Args:
        key: str，调用方传入的 key 参数。

    Returns:
        bool，函数执行后的结果。
    """
    lower = key.lower()
    return any(tok in lower for tok in _SENSITIVE_KEY_TOKENS)


def _redact(value: Any, key: str = "") -> Any:
    """执行 _redact 对应的逻辑，并返回处理结果。

    Args:
        value: Any，调用方传入的 value 参数。
        key: str，调用方传入的 key 参数。

    Returns:
        Any，函数执行后的结果。
    """
    if _is_sensitive_key(key):
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        return "***" if value else value
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item, key) for item in value]
    return value


def spec_to_public_dict(spec: ConnectorSpec) -> dict[str, Any]:
    """执行 spec_to_public_dict 对应的逻辑，并返回处理结果。

    Args:
        spec: ConnectorSpec，调用方传入的 spec 参数。

    Returns:
        dict[str, Any]，函数执行后的结果。
    """
    data = spec.model_dump(mode="json")
    data["config"] = _redact(spec.config or {})
    data["credentials_configured"] = bool(spec.config and spec.config.get("auth_value"))
    return data
