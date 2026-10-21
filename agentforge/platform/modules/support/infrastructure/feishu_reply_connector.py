"""飞书回复连接器模块。"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any


class FeishuReplyConnector:
    """飞书回复连接器实现。"""

    TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
    TOKEN_REFRESH_SKEW_SECONDS = 60

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        request_fn: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        """初始化 FeishuReplyConnector。

        Args:
            app_id: 应用 ID。
            app_secret: 应用密钥。
            request_fn: 请求函数。
        """
        self._app_id = app_id
        self._app_secret = app_secret
        self._request_fn = request_fn
        self._token: str | None = None
        self._token_expires_at = 0.0

    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        """执行请求。

        Args:
            method: HTTP 或业务方法名。
            url: 目标 URL。
            kwargs: 关键字参数。

        Returns:
            处理结果对象。
        """
        if self._request_fn is not None:
            return await self._request_fn(method, url, **kwargs)
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()

    async def _get_token(self) -> str:
        """获取令牌。

        Returns:
            字符串结果。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
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
        """发送文本。

        Args:
            target: 操作目标。
            text: 待处理文本。
            idempotency_key: 幂等键，用于避免重复处理。

        Returns:
            结构化结果字典。
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
        """处理要求成功。

        Args:
            payload: 事件、工作流或请求载荷。
            operation: 操作。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        code = payload.get("code", 0) if isinstance(payload, dict) else None
        if code != 0:
            message = payload.get("msg", "unknown error")
            raise RuntimeError(f"Feishu {operation} failed: {message}")
