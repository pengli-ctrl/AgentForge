"""OIDC模块。"""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


class OIDCAuthenticationError(PermissionError):
    """错误相关组件。"""


@dataclass(frozen=True)
class OIDCPrincipal:
    """OIDC 主体相关组件。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
        subject: 字段值。
        issuer: 字段值。
        roles: 角色。
        permissions: 权限。
        expires_at: 于。
    """

    tenant_id: str
    subject: str
    issuer: str
    roles: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)
    expires_at: datetime | None = None


class OIDCProviderPort(Protocol):
    """OIDC 身份提供方能力端口。"""

    async def authenticate(self, bearer_token: str) -> OIDCPrincipal:
        """认证数据。

        Args:
            bearer_token: 令牌。

        Returns:
            OIDC 主体结果。
        """
        ...


class StaticOIDCProvider:
    """静态相关组件。"""

    def __init__(self, tokens: dict[str, OIDCPrincipal]) -> None:
        """初始化 StaticOIDCProvider。

        Args:
            tokens: 输入参数。
        """
        self._tokens = dict(tokens)

    async def authenticate(self, bearer_token: str) -> OIDCPrincipal:
        """认证静态。

        Args:
            bearer_token: 令牌。

        Returns:
            OIDC 主体结果。

        Raises:
            OIDCAuthenticationError: 操作无法完成时抛出。
        """
        token = bearer_token.strip()
        if not token:
            raise OIDCAuthenticationError("bearer token is required")
        principal: OIDCPrincipal | None = None
        for candidate, value in self._tokens.items():
            if hmac.compare_digest(token, candidate):
                principal = value
                break
        if principal is None:
            raise OIDCAuthenticationError("invalid bearer token")
        if principal.expires_at is not None:
            expires_at = principal.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                raise OIDCAuthenticationError("bearer token expired")
        return principal


def bearer_token(authorization_header: str) -> str:
    """处理令牌。

    Args:
        authorization_header: 输入参数。

    Returns:
        字符串结果。

    Raises:
        OIDCAuthenticationError: 操作无法完成时抛出。
    """
    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise OIDCAuthenticationError("Authorization header must use Bearer scheme")
    return token.strip()


def authorize_principal(principal: OIDCPrincipal, tenant_id: str, permission: str = "") -> None:
    """授权数据。

    Args:
        principal: 当前认证主体。
        tenant_id: 租户 ID，用于数据隔离。
        permission: 权限。

    Raises:
        OIDCAuthenticationError: 操作无法完成时抛出。
    """
    if principal.tenant_id != tenant_id:
        raise OIDCAuthenticationError("OIDC principal is not authorized for tenant")
    if permission and permission not in principal.permissions:
        raise OIDCAuthenticationError("OIDC principal lacks required permission")


__all__ = [
    "OIDCAuthenticationError",
    "OIDCPrincipal",
    "OIDCProviderPort",
    "StaticOIDCProvider",
    "authorize_principal",
    "bearer_token",
]
