"""AgentForge 平台基础设施层：feishu_reply_connector。

本模块封装 feishu_reply_connector 对应外部系统或基础设施协议，提供稳定、可替换的适配接口。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：FeishuReplyConnector。
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any


class FeishuReplyConnector:
    """FeishuReplyConnector。

    FeishuReplyConnector 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

    主要成员：
    - TOKEN_URL: 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'。
    - MESSAGE_URL: 'https://open.feishu.cn/open-apis/im/v1/messages'。
    - TOKEN_REFRESH_SKEW_SECONDS: 60。
    - 方法 send_text()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
    TOKEN_REFRESH_SKEW_SECONDS = 60

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        request_fn: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            app_id: str，调用方传入的 app_id 参数。
            app_secret: str，调用方传入的 app_secret 参数。
            request_fn: Callable[..., Awaitable[Any]] | None，调用方传入的 request_fn 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._app_id = app_id
        self._app_secret = app_secret
        self._request_fn = request_fn
        self._token: str | None = None
        self._token_expires_at = 0.0

    async def _request(self, method: str, url: str, **kwargs) -> Any:
        """执行 _request 对应的逻辑，并返回处理结果。

        Args:
            method: str，调用方传入的 method 参数。
            url: str，调用方传入的 url 参数。
            **kwargs: Any，调用方传入的 **kwargs 参数。

        Returns:
            Any，函数执行后的结果。
        """
        if self._request_fn is not None:
            return await self._request_fn(method, url, **kwargs)
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()

    async def _get_token(self) -> str:
        """执行 _get_token 对应的逻辑，并返回处理结果。

        Returns:
            str，函数执行后的结果。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        payload = await self._request(
            "POST",
            self.TOKEN_URL,
            json={"app_id": self._app_id, "app_secret": self._app_secret},
        )
        self._require_success(payload, "tenant access token request")
        token = payload.get("tenant_access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("Feishu tenant access token response is missing a token")
        expire_seconds = float(payload.get("expire", 7200))
        self._token = token
        self._token_expires_at = time.monotonic() + max(
            expire_seconds - self.TOKEN_REFRESH_SKEW_SECONDS,
            0,
        )
        return self._token

    async def send_text(self, target: str, text: str, idempotency_key: str) -> dict:
        """执行 send_text 对应的逻辑，并返回处理结果。

        Args:
            target: str，调用方传入的 target 参数。
            text: str，调用方传入的 text 参数。
            idempotency_key: str，调用方传入的 idempotency_key 参数。

        Returns:
            dict，函数执行后的结果。
        """
        token = await self._get_token()
        payload = await self._request(
            "POST",
            self.MESSAGE_URL,
            params={"receive_id_type": "chat_id", "uuid": idempotency_key},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": target,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            },
        )
        self._require_success(payload, "message send")
        data = payload.get("data") or {}
        return {
            "message_id": data.get("message_id", ""),
            "raw": payload,
        }

    @staticmethod
    def _require_success(payload: Any, operation: str) -> None:
        """执行 _require_success 对应的逻辑，并返回处理结果。

        Args:
            payload: Any，调用方传入的 payload 参数。
            operation: str，调用方传入的 operation 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        code = payload.get("code", 0) if isinstance(payload, dict) else None
        if code != 0:
            message = payload.get("msg", "unknown error")
            raise RuntimeError(f"Feishu {operation} failed: {message}")
