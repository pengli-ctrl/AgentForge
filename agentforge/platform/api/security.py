from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException, Request


class ApiKeyAuthenticator:
    def __init__(
        self,
        enabled: bool,
        tenant_keys: dict[str, str] | None = None,
        admin_key: str = "",
    ) -> None:
        self._enabled = enabled
        self._tenant_keys = dict(tenant_keys or {})
        self._admin_key = admin_key
        if enabled and not self._tenant_keys and not self._admin_key:
            raise ValueError("Authentication requires at least one API key")

    def authorize_tenant(self, request: Request, tenant_id: str) -> None:
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
        if not self._enabled:
            return
        if not self._admin_key or self._read_key(request) != self._admin_key:
            raise HTTPException(status_code=401, detail="Invalid admin API key")

    @staticmethod
    def _read_key(request: Request) -> str:
        return request.headers.get("X-API-Key", "")


def verify_event_hmac(raw_body: bytes, secret: str, provided: str) -> bool:
    """Verify an HMAC-SHA256 signature over the raw request body.

    When ``secret`` is empty (nothing configured) verification cannot be
    performed; the caller treats that as a pass-through for dev/local
    environments. When a secret is configured, a missing or mismatched
    ``provided`` signature is rejected. Used for the generic IM webhook to
    align the endpoint's behaviour with its documented "HMAC 验签" contract.
    """
    if not secret:
        return True
    if not provided:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)
