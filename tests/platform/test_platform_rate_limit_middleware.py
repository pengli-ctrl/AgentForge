"""测试平台限流中间件。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentforge.platform.api.rate_limit_middleware import PlatformRateLimitMiddleware


class DenyBackend:
    """提供拒绝全部请求的限流后端。"""

    async def acquire(self, key):
        """拒绝请求。

        Args:
            key: 限流键。

        Returns:
            拒绝结果。
        """

        class Decision:
            """提供限流拒绝结果。"""

            allowed = False
            retry_after_ms = 2500

        return Decision()


def test_platform_rate_limit_returns_429() -> None:
    """验证限流中间件返回 429。"""
    app = FastAPI()
    app.add_middleware(PlatformRateLimitMiddleware, backend=DenyBackend())

    @app.get("/health")
    def health():
        """返回健康状态。"""
        return {"ok": True}

    response = TestClient(app).get("/health", headers={"X-API-Key": "k1"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "2"
