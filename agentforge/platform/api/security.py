"""AgentForge 平台 API 层：security。

本模块负责 security 相关的平台能力，是 平台 API 层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：ApiKeyAuthenticator。
- 主要函数：verify_event_hmac。
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException, Request


class ApiKeyAuthenticator:
    """ApiKeyAuthenticator。

    ApiKeyAuthenticator 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 authorize_tenant()。
    - 方法 authorize_admin()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        enabled: bool,
        tenant_keys: dict[str, str] | None = None,
        admin_key: str = "",
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            enabled: bool，调用方传入的 enabled 参数。
            tenant_keys: dict[str, str] | None，调用方传入的 tenant_keys 参数。
            admin_key: str，调用方传入的 admin_key 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        self._enabled = enabled
        self._tenant_keys = dict(tenant_keys or {})
        self._admin_key = admin_key
        if enabled and not self._tenant_keys and not self._admin_key:
            raise ValueError("Authentication requires at least one API key")

    def authorize_tenant(self, request: Request, tenant_id: str) -> None:
        """执行 authorize_tenant 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
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
        """执行 authorize_admin 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if not self._enabled:
            return
        if not self._admin_key or self._read_key(request) != self._admin_key:
            raise HTTPException(status_code=401, detail="Invalid admin API key")

    @staticmethod
    def _read_key(request: Request) -> str:
        """执行 _read_key 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。

        Returns:
            str，函数执行后的结果。
        """
        return request.headers.get("X-API-Key", "")


def verify_event_hmac(raw_body: bytes, secret: str, provided: str) -> bool:
    """执行 verify_event_hmac 对应的逻辑，并返回处理结果。

    Args:
        raw_body: bytes，调用方传入的 raw_body 参数。
        secret: str，调用方传入的 secret 参数。
        provided: str，调用方传入的 provided 参数。

    Returns:
        bool，函数执行后的结果。
    """
    if not secret:
        return True
    if not provided:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)
