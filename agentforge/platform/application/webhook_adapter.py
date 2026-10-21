"""Webhook适配器模块。"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from agentforge.platform.domain.connector import WebhookDelivery


class WebhookSignatureVerifier:
    """Webhook签名核验器相关组件。"""

    def __init__(
        self,
        secret_provider: Any | None = None,
        default_secret: str | None = None,
    ) -> None:
        """初始化 WebhookSignatureVerifier。

        Args:
            secret_provider: 密钥提供方。
            default_secret: 默认密钥。
        """
        self._secret_provider = secret_provider
        self._default_secret = default_secret

    def _secret_for(self, tenant_id: str) -> str | None:
        """处理密钥用于。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            无结果。
        """
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
        """校验Webhook签名核验器。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            timestamp: 输入参数。
            nonce: 输入参数。
            body: 请求体数据。
            signature: 签名。

        Returns:
            操作是否成功。
        """
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
    """Webhook集成适配器。"""

    def __init__(
        self,
        source: str,
        parse_factory: Any | None = None,
    ) -> None:
        """初始化 WebhookAdapter。

        Args:
            source: 调用或事件来源。
            parse_factory: 解析工厂。
        """
        self._source = source
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
        """解析Webhook。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            payload: 事件、工作流或请求载荷。
            event_id: 事件 ID。
            text: 待处理文本。
            conversation_id: 会话 ID。
            customer_id: 客户 ID。
            source: 调用或事件来源。

        Returns:
            Webhook结果。
        """
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
    """处理通用文本解析器。

    Args:
        payload: 事件、工作流或请求载荷。

    Returns:
        结构化结果字典。
    """
    return {
        "event_id": payload.get("event_id", ""),
        "text": payload.get("text", ""),
        "conversation_id": payload.get("conversation_id", ""),
        "customer_id": payload.get("customer_id", ""),
    }
