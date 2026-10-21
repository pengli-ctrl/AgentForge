"""安全模块。"""

from __future__ import annotations

from fastapi import HTTPException, Request

from agentforge.platform.sdk.security import verify_event_hmac as verify_event_hmac

__all__ = ["ApiKeyAuthenticator", "verify_event_hmac"]


class ApiKeyAuthenticator:
    """API键认证器相关组件。"""

    def __init__(
        self,
        enabled: bool,
        tenant_keys: dict[str, str] | None = None,
        admin_key: str = "",
    ) -> None:
        """初始化 ApiKeyAuthenticator。

        Args:
            enabled: 启用。
            tenant_keys: 租户键。
            admin_key: 管理键。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        self._enabled = enabled
        self._tenant_keys = dict(tenant_keys or {})
        self._admin_key = admin_key
        if enabled and not self._tenant_keys and not self._admin_key:
            raise ValueError("Authentication requires at least one API key")

    def authorize_tenant(self, request: Request, tenant_id: str) -> None:
        """授权租户。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        if not self._enabled:
            return
        api_key = self._read_key(request)
        if api_key == self._admin_key and self._admin_key:
            return
        authorized_tenant = self._tenant_keys.get(api_key)
        if authorized_tenant is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        if authorized_tenant != tenant_id:
            raise HTTPException(status_code=403, detail="API key is not authorized for tenant")

    def authorize_admin(self, request: Request) -> None:
        """授权管理。

        Args:
            request: 当前 HTTP 请求。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        if not self._enabled:
            return
        if not self._admin_key or self._read_key(request) != self._admin_key:
            raise HTTPException(status_code=401, detail="Invalid admin API key")

    @staticmethod
    def _read_key(request: Request) -> str:
        """读取键。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            字符串结果。
        """
        return request.headers.get("X-API-Key", "")
