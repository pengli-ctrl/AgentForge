"""Webhook通知网关模块。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class WebhookNotificationGateway:
    """Webhook通知网关抽象。"""

    def __init__(
        self,
        endpoint: str,
        *,
        token: str = "",
        timeout_seconds: float = 10.0,
        request_fn: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        """初始化 WebhookNotificationGateway。

        Args:
            endpoint: 端点。
            token: 待验证的访问令牌。
            timeout_seconds: 超时。
            request_fn: 请求函数。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if not endpoint.strip():
            raise ValueError("notification webhook endpoint is required")
        self._endpoint = endpoint.strip()
        self._token = token.strip()
        self._timeout_seconds = max(0.1, timeout_seconds)
        self._request_fn = request_fn

    async def send(
        self,
        *,
        tenant_id: str,
        ticket_id: str,
        event_type: str,
        idempotency_key: str,
        text: str,
        payload: dict[str, object],
        target: str | None = None,
    ) -> dict[str, object]:
        """发送Webhook通知。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            ticket_id: 工单 ID。
            event_type: 事件类型。
            idempotency_key: 幂等键，用于避免重复处理。
            text: 待处理文本。
            payload: 事件、工作流或请求载荷。
            target: 操作目标。

        Returns:
            结构化结果字典。
        """
        body = {
            "tenant_id": tenant_id,
            "ticket_id": ticket_id,
            "event_type": event_type,
            "text": text,
            "target": target,
            "payload": payload,
        }
        headers = {
            "X-Idempotency-Key": idempotency_key,
            "X-AgentForge-Event": event_type,
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if self._request_fn is not None:
            response = await self._request_fn(
                "POST",
                self._endpoint,
                headers=headers,
                json=body,
            )
        else:
            import httpx

            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(self._endpoint, headers=headers, json=body)
                response.raise_for_status()
        return {
            "delivered": True,
            "status_code": int(getattr(response, "status_code", 200)),
            "idempotent_replay": False,
        }
