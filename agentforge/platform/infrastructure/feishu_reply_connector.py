from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any


class FeishuReplyConnector:
    TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
    TOKEN_REFRESH_SKEW_SECONDS = 60

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        request_fn: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._request_fn = request_fn
        self._token: str | None = None
        self._token_expires_at = 0.0

    async def _request(self, method: str, url: str, **kwargs) -> Any:
        if self._request_fn is not None:
            return await self._request_fn(method, url, **kwargs)
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()

    async def _get_token(self) -> str:
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
        code = payload.get("code", 0) if isinstance(payload, dict) else None
        if code != 0:
            message = payload.get("msg", "unknown error")
            raise RuntimeError(f"Feishu {operation} failed: {message}")
