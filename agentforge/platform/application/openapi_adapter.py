"""AgentForge 平台应用服务层：openapi_adapter。

本模块封装 openapi_adapter 对应外部系统或基础设施协议，提供稳定、可替换的适配接口。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：OpenAPIAdapter。
- 主要函数：build_openapi_adapter。
"""

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
    """OpenAPIAdapter。

    OpenAPIAdapter 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

    主要成员：
    - name: str。
    - version: str。
    - risk_level: str。
    - IDEMPOTENCY_HEADER: 'X-Idempotency-Key'。
    - 方法 health()。
    - 方法 invoke()。
    - 方法 compensate()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            endpoint: str，调用方传入的 endpoint 参数。
            headers: dict[str, str] | None，调用方传入的 headers 参数。
            auth_header: str | None，调用方传入的 auth_header 参数。
            auth_value_provider: Callable[[], str] | None，调用方传入的 auth_value_provider 参数。
            timeout_seconds: float，调用方传入的 timeout_seconds 参数。
            max_retries: int，调用方传入的 max_retries 参数。
            retry_backoff_seconds: float，调用方传入的 retry_backoff_seconds 参数。
            rate_per_second: float | None，调用方传入的 rate_per_second 参数。
            audit_sink: Callable[[dict[str, Any]], Awaitable[None]] | None，调用方传入的 audit_sink 参数。
            request_fn: RequestFn | None，调用方传入的 request_fn 参数。

        Returns:
            None，函数执行后的结果。
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

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()

    def _acquire_token(self) -> bool:
        """执行 _acquire_token 对应的逻辑，并返回处理结果。

        Returns:
            bool，函数执行后的结果。
        """
        if self._rate_per_second is None:
            return True
        now = time.monotonic()
        elapsed = now - self._bucket_updated
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
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
        """执行 _build_headers 对应的逻辑，并返回处理结果。

        Args:
            context: ConnectorContext，调用方传入的 context 参数。

        Returns:
            dict[str, str]，函数执行后的结果。
        """
        headers = dict(self._headers)
        if context.idempotency_key:
            headers[self.IDEMPOTENCY_HEADER] = context.idempotency_key
        if self._auth_header and self._auth_value_provider is not None:
            headers[self._auth_header] = self._auth_value_provider()
        return headers

    async def health(self) -> ConnectorHealth:
        """执行 health 对应的逻辑，并返回处理结果。

        Returns:
            ConnectorHealth，函数执行后的结果。
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
        """执行 invoke 对应的逻辑，并返回处理结果。

        Args:
            action: str，调用方传入的 action 参数。
            payload: dict，调用方传入的 payload 参数。
            context: ConnectorContext，调用方传入的 context 参数。

        Returns:
            ConnectorInvocationResult，函数执行后的结果。
        """
        spec = payload.get("method", "GET").upper()
        path = payload.get("path", "/")
        body = payload.get("body", payload)
        url = f"{self._endpoint}{path}"
        headers = self._build_headers(context)

        last_error: str | None = None
        for attempt in range(self._max_retries + 1):
            if not self._acquire_token():
                # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
                # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
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
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        """执行 compensate 对应的逻辑，并返回处理结果。

        Args:
            action: str，调用方传入的 action 参数。
            payload: dict，调用方传入的 payload 参数。
            context: ConnectorContext，调用方传入的 context 参数。

        Returns:
            ConnectorInvocationResult，函数执行后的结果。
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
        """执行 _audit 对应的逻辑，并返回处理结果。

        Args:
            action: str，调用方传入的 action 参数。
            context: ConnectorContext，调用方传入的 context 参数。
            ok: bool，调用方传入的 ok 参数。
            data: Any，调用方传入的 data 参数。
            error: str | None，调用方传入的 error 参数。

        Returns:
            None，函数执行后的结果。
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
    """构建目标对象，并返回调用方需要的结果。

    Args:
        spec: ConnectorSpec，调用方传入的 spec 参数。
        auth_value_provider: Callable[[], str] | None，调用方传入的 auth_value_provider 参数。

    Returns:
        OpenAPIAdapter，函数执行后的结果。
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
