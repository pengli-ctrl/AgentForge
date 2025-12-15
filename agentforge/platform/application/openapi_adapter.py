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
    """Generic HTTP/OpenAPI connector adapter.

    Implements the Connector SDK contract over arbitrary HTTP endpoints. It
    honors idempotency keys (forwarded as a header), supports bounded retry
    with backoff, reference-based credentials, a token-bucket rate limiter, and
    an optional audit sink. Meant for write-back / read actions against CRMs,
    ticketing systems, or OpenAPI services.
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
        if self._request_fn is not None:
            return await self._request_fn(method, url, **kwargs)
        import httpx

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()

    def _acquire_token(self) -> bool:
        """Consume one token from the rate-limit bucket if available.

        Refills at ``rate_per_second`` up to ``_bucket_capacity`` (a token
        bucket), then returns True and consumes a token when at least one is
        available, or False when the bucket is empty so the caller backs off.
        When no rate is configured the call always succeeds (unlimited).
        """
        if self._rate_per_second is None:
            return True
        now = time.monotonic()
        elapsed = now - self._bucket_updated
        # Refill proportionally to elapsed time, capped at capacity so tokens
        # never accumulate beyond a burst.
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
        headers = dict(self._headers)
        if context.idempotency_key:
            headers[self.IDEMPOTENCY_HEADER] = context.idempotency_key
        if self._auth_header and self._auth_value_provider is not None:
            headers[self._auth_header] = self._auth_value_provider()
        return headers

    async def health(self) -> ConnectorHealth:
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
        spec = payload.get("method", "GET").upper()
        path = payload.get("path", "/")
        body = payload.get("body", payload)
        url = f"{self._endpoint}{path}"
        headers = self._build_headers(context)

        last_error: str | None = None
        for attempt in range(self._max_retries + 1):
            if not self._acquire_token():
                # Token bucket exhausted: back off and retry on a later window
                # rather than firing an unbounded request.
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
        # Compensate reuses the given payload; callers may pass a
        # compensating operation (e.g. reversal action) in the payload.
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
    """Reconstruct an OpenAPIAdapter from a persisted ConnectorSpec."""
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
