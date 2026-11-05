"""提供架构升级适配。"""

from __future__ import annotations

from fastapi import HTTPException, Request

from agentforge.platform.sdk.security import verify_event_hmac as verify_event_hmac

__all__ = ["ApiKeyAuthenticator", "OIDCAuthenticator", "build_authenticator", "verify_event_hmac"]


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


class OIDCAuthenticator(ApiKeyAuthenticator):
    """提供 OIDC Bearer 认证和 API Key 兼容回退。"""

    def __init__(self, *, enabled: bool, token_validator, fallback: ApiKeyAuthenticator | None = None, tenant_claim: str = "tenant_id") -> None:
        """提供架构升级适配。

        Args:
            enabled: 输入参数。
            token_validator: 输入参数。
            fallback: 输入参数。
            tenant_claim: 输入参数。
        """
        self._enabled = enabled
        self._token_validator = token_validator
        self._fallback = fallback
        self._tenant_claim = tenant_claim

    def authorize_tenant(self, request: Request, tenant_id: str) -> None:
        """提供架构升级适配。

        Args:
            request: 输入参数。
            tenant_id: 输入参数。

        Raises:
    ValueError: 输入不合法时抛出。
        """
        if not self._enabled:
            return
        token = self._read_bearer(request)
        if token:
            claims = self._token_validator(token)
            claim_tenant = str(claims.get(self._tenant_claim) or "")
            if not claim_tenant:
                raise HTTPException(status_code=403, detail="OIDC token is missing tenant claim")
            if claim_tenant != tenant_id:
                raise HTTPException(status_code=403, detail="OIDC token is not authorized for tenant")
            return
        if self._fallback is not None:
            self._fallback.authorize_tenant(request, tenant_id)
            return
        raise HTTPException(status_code=401, detail="Missing bearer token")

    def authorize_admin(self, request: Request) -> None:
        """提供架构升级适配。

        Args:
            request: 输入参数。

        Raises:
    ValueError: 输入不合法时抛出。
        """
        if not self._enabled:
            return
        token = self._read_bearer(request)
        if token:
            claims = self._token_validator(token)
            roles = claims.get("roles", [])
            if isinstance(roles, str):
                roles = [roles]
            if "admin" not in roles:
                raise HTTPException(status_code=403, detail="OIDC token lacks admin role")
            return
        if self._fallback is not None:
            self._fallback.authorize_admin(request)
            return
        raise HTTPException(status_code=401, detail="Missing bearer token")

    @staticmethod
    def _read_bearer(request: Request) -> str:
        """提供架构升级适配。

        Args:
            request: 输入参数。

        Returns:
    处理结果。
        """
        header = request.headers.get("Authorization", "")
        if not header.lower().startswith("bearer "):
            return ""
        return header[7:].strip()


def build_authenticator(settings, *, enabled: bool | None = None) -> ApiKeyAuthenticator:
    """根据配置选择认证模式。

    Args:
        settings: 平台配置。
        enabled: 是否启用认证。

    Returns:
        认证器实例。

    Raises:
        ValueError: 认证模式不支持时抛出。
    """
    api_key = ApiKeyAuthenticator(
        enabled=settings.auth_enabled if enabled is None else enabled,
        tenant_keys=settings.api_keys,
        admin_key=settings.admin_api_key,
    )
    if settings.auth_mode == "api_key":
        return api_key
    if settings.auth_mode == "hybrid":
        return api_key
    if settings.auth_mode == "oidc":
        raise ValueError("oidc mode requires an injected OIDC token validator")
    raise ValueError(f"unsupported auth_mode: {settings.auth_mode}")
