"""OPA policy adapter.

The adapter is deliberately small and injectable so existing local policy
decisions remain the default until an OPA endpoint and policy package are ready.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import httpx

from agentforge.platform.domain.authorization import AuthorizationDecision, AuthorizationOutcome


class OPAPolicyAdapter:
    def __init__(self, base_url: str, policy_path: str = "agentforge/allow", client: httpx.AsyncClient | None = None) -> None:
        self._url = f"{base_url.rstrip('/')}/v1/data/{policy_path.strip('/')}"
        self._client = client or httpx.AsyncClient(timeout=2.0)
        self._owns_client = client is None

    async def authorize(self, *, tenant_id: str, principal: str, action: str, resource_type: str, resource_id: str, context: Mapping[str, Any] | None = None) -> AuthorizationDecision:
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
        if self._owns_client:
            await self._client.aclose()
