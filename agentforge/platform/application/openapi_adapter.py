"""OpenAPI适配器模块。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from agentforge.platform.application.connector_registry import Connector
from agentforge.platform.domain.connector import (
    ConnectorContext,
    ConnectorHealth,
    ConnectorInvocationResult,
    ConnectorSpec,
)

RequestFn = Callable[..., Awaitable[Any]]


class OpenAPIAdapter(Connector):
    """打开API 适配器相关组件。

    Attributes:
        name: 名称。
        version: 版本号。
        risk_level: 风险级别。
    """

    name: str = "openapi"
    version: str = "1.0"
    risk_level: str = "medium"

    IDEMPOTENCY_HEADER = "X-Idempotency-Key"

    def __init__(
        self,
        endpoint: str,
        *,
        headers: dict[str, str] | None = None,
        auth_header: str | None = None,
        auth_value_provider: Callable[[], str] | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.05,
        rate_per_second: float | None = None,
        audit_sink: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        request_fn: RequestFn | None = None,
    ) -> None:
        """初始化 OpenAPIAdapter。

        Args:
            endpoint: 端点。
            headers: 输入参数。
            auth_header: 鉴权。
            auth_value_provider: 鉴权值提供方。
            timeout_seconds: 超时。
            max_retries: 最大重试。
            retry_backoff_seconds: 重试。
            rate_per_second: 速率第二。
            audit_sink: 审计接收器。
            request_fn: 请求函数。
        """
        self._endpoint = endpoint.rstrip("/")
        self._headers = dict(headers or {})
        self._auth_header = auth_header
        self._auth_value_provider = auth_value_provider
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff_seconds
        self._request_fn = request_fn
        self._audit_sink = audit_sink
        self._rate_per_second = rate_per_second
        if rate_per_second and rate_per_second > 0:
            self._bucket_capacity = float(rate_per_second)
            self._bucket_tokens = float(rate_per_second)
            self._bucket_updated = time.monotonic()
        else:
            self._rate_per_second = None

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

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()

    def _acquire_token(self) -> bool:
        """判断令牌是否成立。

        Returns:
            操作是否成功。
        """
        if self._rate_per_second is None:
            return True
        now = time.monotonic()
        elapsed = now - self._bucket_updated
        self._bucket_tokens = min(
            self._bucket_capacity,
            self._bucket_tokens + elapsed * self._rate_per_second,
        )
        self._bucket_updated = now
        if self._bucket_tokens < 1.0:
            return False
        self._bucket_tokens -= 1.0
        return True

    def _build_headers(self, context: ConnectorContext) -> dict[str, str]:
        """构建打开API 适配器。

        Args:
            context: 执行上下文。

        Returns:
            结构化结果字典。
        """
        headers = dict(self._headers)
        if context.idempotency_key:
            headers[self.IDEMPOTENCY_HEADER] = context.idempotency_key
        if self._auth_header and self._auth_value_provider is not None:
            headers[self._auth_header] = self._auth_value_provider()
        return headers

    async def health(self) -> ConnectorHealth:
        """检查打开API 适配器健康状态。

        Returns:
            连接器健康结果。
        """
        return ConnectorHealth(
            connector_id="openapi",
            healthy=bool(self._endpoint),
            detail=f"endpoint={self._endpoint or 'unset'}",
        )

    async def invoke(
        self,
        action: str,
        payload: dict,
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        """调用打开API 适配器。

        Args:
            action: 待执行动作名称。
            payload: 事件、工作流或请求载荷。
            context: 执行上下文。

        Returns:
            连接器结果结果。
        """
        spec = payload.get("method", "GET").upper()
        path = payload.get("path", "/")
        body = payload.get("body", payload)
        url = f"{self._endpoint}{path}"
        headers = self._build_headers(context)

        last_error: str | None = None
        for attempt in range(self._max_retries + 1):
            if not self._acquire_token():
                await asyncio.sleep(self._retry_backoff * (2**attempt))
                last_error = "rate limited"
                continue
            try:
                data = await self._request(
                    spec,
                    url,
                    headers=headers,
                    json=body if spec in {"POST", "PUT", "PATCH"} else None,
                    params=payload.get("params"),
                )
                await self._audit(action, context, ok=True, data=data)
                return ConnectorInvocationResult(
                    connector_id="openapi",
                    action=action,
                    ok=True,
                    data=data if isinstance(data, dict) else {"value": data},
                )
            except Exception as exc:  # noqa: BLE001 - surface as result error
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_backoff * (2**attempt))
        await self._audit(action, context, ok=False, error=last_error)
        return ConnectorInvocationResult(
            connector_id="openapi",
            action=action,
            ok=False,
            error=last_error,
        )

    async def compensate(
        self,
        action: str,
        payload: dict,
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        """补偿打开API 适配器。

        Args:
            action: 待执行动作名称。
            payload: 事件、工作流或请求载荷。
            context: 执行上下文。

        Returns:
            连接器结果结果。
        """
        result = await self.invoke(action, payload, context)
        return result

    async def _audit(
        self,
        action: str,
        context: ConnectorContext,
        *,
        ok: bool,
        data: Any = None,
        error: str | None = None,
    ) -> None:
        """审计打开API 适配器。

        Args:
            action: 待执行动作名称。
            context: 执行上下文。
            ok: 输入参数。
            data: 待处理数据。
            error: 错误。
        """
        if self._audit_sink is None:
            return
        try:
            await self._audit_sink(
                {
                    "connector": self.name,
                    "action": action,
                    "tenant_id": context.tenant_id,
                    "task_id": context.task_id,
                    "trace_id": context.trace_id,
                    "idempotency_key": context.idempotency_key,
                    "ok": ok,
                    "data": data if ok else None,
                    "error": error,
                }
            )
        except Exception:  # noqa: BLE001 - never let audit break the call
            pass


def build_openapi_adapter(
    spec: ConnectorSpec,
    auth_value_provider: Callable[[], str] | None = None,
) -> OpenAPIAdapter:
    """构建OpenAPI适配器。

    Args:
        spec: 资源规格定义。
        auth_value_provider: 鉴权值提供方。

    Returns:
        打开API 适配器结果。
    """
    config = spec.config or {}
    if auth_value_provider is None:
        static_value = config.get("auth_value")
        if static_value:
            auth_value_provider = lambda: str(static_value)  # noqa: E731
    return OpenAPIAdapter(
        spec.endpoint or "",
        headers=dict(config.get("headers") or {}),
        auth_header=config.get("auth_header"),
        auth_value_provider=auth_value_provider,
        timeout_seconds=float(config.get("timeout_seconds") or 30.0),
        max_retries=int(config.get("max_retries") or 2),
        retry_backoff_seconds=float(config.get("retry_backoff_seconds") or 0.05),
        rate_per_second=float(config["rate_per_second"]) if config.get("rate_per_second") else None,
    )
