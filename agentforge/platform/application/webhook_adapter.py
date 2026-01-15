"""AgentForge 平台应用服务层：webhook_adapter。

本模块封装 webhook_adapter 对应外部系统或基础设施协议，提供稳定、可替换的适配接口。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：WebhookSignatureVerifier、WebhookAdapter。
- 主要函数：generic_text_parser。
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from agentforge.platform.domain.connector import WebhookDelivery


class WebhookSignatureVerifier:
    """WebhookSignatureVerifier。

    WebhookSignatureVerifier 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 verify()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        secret_provider: Any | None = None,
        default_secret: str | None = None,
    ) -> None:
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            secret_provider: Any | None，调用方传入的 secret_provider 参数。
            default_secret: str | None，调用方传入的 default_secret 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._secret_provider = secret_provider
        self._default_secret = default_secret

    def _secret_for(self, tenant_id: str) -> str | None:
        """执行 _secret_for 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            str | None，函数执行后的结果。
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
        """执行 verify 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            timestamp: str，调用方传入的 timestamp 参数。
            nonce: str，调用方传入的 nonce 参数。
            body: bytes，调用方传入的 body 参数。
            signature: str，调用方传入的 signature 参数。

        Returns:
            bool，函数执行后的结果。
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
    """WebhookAdapter。

    WebhookAdapter 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

    主要成员：
    - 方法 parse()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        source: str,
        parse_factory: Any | None = None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            source: str，调用方传入的 source 参数。
            parse_factory: Any | None，调用方传入的 parse_factory 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._source = source
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
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
        """执行 parse 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            payload: dict[str, Any]，调用方传入的 payload 参数。
            event_id: str，调用方传入的 event_id 参数。
            text: str，调用方传入的 text 参数。
            conversation_id: str，调用方传入的 conversation_id 参数。
            customer_id: str，调用方传入的 customer_id 参数。
            source: str | None，调用方传入的 source 参数。

        Returns:
            WebhookDelivery，函数执行后的结果。
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
    """执行 generic_text_parser 对应的逻辑，并返回处理结果。

    Args:
        payload: dict[str, Any]，调用方传入的 payload 参数。

    Returns:
        dict[str, Any]，函数执行后的结果。
    """
    return {
        "event_id": payload.get("event_id", ""),
        "text": payload.get("text", ""),
        "conversation_id": payload.get("conversation_id", ""),
        "customer_id": payload.get("customer_id", ""),
    }
