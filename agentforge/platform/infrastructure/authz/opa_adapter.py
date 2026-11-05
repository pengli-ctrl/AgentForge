"""提供架构升级适配。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import httpx

from agentforge.platform.domain.authorization import AuthorizationDecision, AuthorizationOutcome


class OPAPolicyAdapter:
    """提供架构升级适配。
    """
    def __init__(self, base_url: str, policy_path: str = "agentforge/allow", client: httpx.AsyncClient | None = None) -> None:
        """提供架构升级适配。

        Args:
            base_url: 输入参数。
            policy_path: 输入参数。
            client: 输入参数。
        """
        self._url = f"{base_url.rstrip('/')}/v1/data/{policy_path.strip('/')}"
        self._client = client or httpx.AsyncClient(timeout=2.0)
        self._owns_client = client is None

    async def authorize(self, *, tenant_id: str, principal: str, action: str, resource_type: str, resource_id: str, context: Mapping[str, Any] | None = None) -> AuthorizationDecision:
        """提供架构升级适配。

        Args:
            tenant_id: 输入参数。
            principal: 输入参数。
            action: 输入参数。
            resource_type: 输入参数。
            resource_id: 输入参数。
            context: 输入参数。

        Returns:
    处理结果。
        """
        response = await self._client.post(self._url, json={"input": {"tenant_id": tenant_id, "principal": principal, "action": action, "resource_type": resource_type, "resource_id": resource_id, "context": dict(context or {})}})
        response.raise_for_status()
        result = response.json().get("result", {})
        outcome = AuthorizationOutcome(str(result.get("outcome", "denied")))
        return AuthorizationDecision(
            authorization_id=str(uuid4()),
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            principal=principal,
            outcome=outcome,
            reasons=[str(reason) for reason in result.get("reasons", [])],
            approval_ref=result.get("approval_ref"),
        )

    async def close(self) -> None:
        """提供架构升级适配。
        """
        if self._owns_client:
            await self._client.aclose()
