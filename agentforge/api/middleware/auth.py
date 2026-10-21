"""鉴权模块。"""

from __future__ import annotations

import logging
import secrets

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """API Key 认证中间件。

    Attributes:
        PUBLIC_PATHS: 公共。
    """

    # 不需要认证的路径
    PUBLIC_PATHS: set[str] = {"/", "/health", "/docs", "/openapi.json", "/redoc"}

    def __init__(
        self,
        api_keys: set[str] | None = None,
        allow_no_auth: bool = False,
    ) -> None:
        """初始化 AuthMiddleware。

        Args:
            api_keys: API键。
            allow_no_auth: 允许无鉴权。
        """
        self.api_keys = api_keys or set()
        self.allow_no_auth = allow_no_auth

    def authenticate(self, headers: dict[str, str], path: str) -> bool:
        """认证请求。

        Args:
            headers: 输入参数。
            path: 文件或资源路径。

        Returns:
            操作是否成功。
        """
        # 公开路径不需要认证
        if path in self.PUBLIC_PATHS:
            return True

        # 开发环境允许跳过认证
        if self.allow_no_auth and not self.api_keys:
            return True

        # 提取 API Key
        api_key = self._extract_api_key(headers)
        if api_key is None:
            logger.warning("Authentication failed: no API key in request (path=%s)", path)
            return False

        # 使用恒定时间比较防止时序攻击
        for valid_key in self.api_keys:
            if secrets.compare_digest(api_key, valid_key):
                return True

        logger.warning("Authentication failed: invalid API key (path=%s)", path)
        return False

    def _extract_api_key(self, headers: dict[str, str]) -> str | None:
        """从请求头提取 API Key。

        Args:
            headers: 输入参数。

        Returns:
            无结果。
        """
        # 方式 1: X-API-Key 头
        api_key = headers.get("x-api-key") or headers.get("X-API-Key")
        if api_key:
            return api_key.strip()

        # 方式 2: Authorization Bearer
        auth_header = headers.get("authorization") or headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:].strip()

        return None

    @staticmethod
    def generate_api_key() -> str:
        """生成一个新的 API Key。

        Returns:
            字符串结果。
        """
        return secrets.token_urlsafe(24)
