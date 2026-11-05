"""平台请求限流中间件。"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class PlatformRateLimitMiddleware(BaseHTTPMiddleware):
    """为平台 API 提供可替换的请求级限流。"""

    def __init__(self, app, backend) -> None:
        """初始化限流中间件。

        Args:
            app: ASGI 应用。
            backend: 限流后端。
        """
        super().__init__(app)
        self._backend = backend

    async def dispatch(self, request: Request, call_next):
        """执行请求限流。

        Args:
            request: 当前请求。
            call_next: 下游处理函数。

        Returns:
            响应对象。
        """
        key = request.headers.get("X-API-Key") or request.headers.get("X-Tenant-ID") or "anonymous"
        decision = await self._backend.acquire(key)
        if not decision.allowed:
            return JSONResponse(
                status_code=429,
                content={"code": "RATE_LIMITED", "message": "Rate limit exceeded"},
                headers={"Retry-After": str(max(1, decision.retry_after_ms // 1000))},
            )
        return await call_next(request)
