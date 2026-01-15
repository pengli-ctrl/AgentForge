"""API Key 认证中间件 — 基于 API Key 的请求认证。

从请求头 X-API-Key 或 Authorization: Bearer <key> 提取 API Key，
与配置的合法 Key 列表比对。

设计原则：
- 开发环境可禁用认证（设置 allow_no_auth=True）
- 生产环境必须配置 API Key
- 认证失败返回 401 Unauthorized
"""

from __future__ import annotations

import logging
import secrets

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """API Key 认证中间件。

    支持两种 Key 传递方式：
    - 请求头 X-API-Key: <key>
    - Authorization: Bearer <key>

    Args:
        api_keys: 合法的 API Key 集合。
        allow_no_auth: 是否允许无认证访问（仅开发环境）。
    """

    # 不需要认证的路径
    PUBLIC_PATHS: set[str] = {"/", "/health", "/docs", "/openapi.json", "/redoc"}

    def __init__(
        self,
        api_keys: set[str] | None = None,
        allow_no_auth: bool = False,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            api_keys: set[str] | None，调用方传入的 api_keys 参数。
            allow_no_auth: bool，调用方传入的 allow_no_auth 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.api_keys = api_keys or set()
        self.allow_no_auth = allow_no_auth

    def authenticate(self, headers: dict[str, str], path: str) -> bool:
        """认证请求。

        Args:
            headers: 请求头字典。
            path: 请求路径。

        Returns:
            是否认证通过。
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

        支持两种格式：
        - X-API-Key: <key>
        - Authorization: Bearer <key>

        Args:
            headers: 请求头字典。

        Returns:
            API Key 字符串，不存在则返回 None。
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
            32 字符的随机 API Key。
        """
        return secrets.token_urlsafe(24)
