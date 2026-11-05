from starlette.requests import Request

from agentforge.platform.api.security import ApiKeyAuthenticator, OIDCAuthenticator


def _request(authorization: str = "") -> Request:
    return Request({"type": "http", "headers": [(b"authorization", authorization.encode())]})


def test_oidc_accepts_matching_tenant_claim() -> None:
    authenticator = OIDCAuthenticator(enabled=True, token_validator=lambda token: {"tenant_id": "tenant-a", "roles": ["admin"]})
    authenticator.authorize_tenant(_request("Bearer valid-token"), "tenant-a")
    authenticator.authorize_admin(_request("Bearer valid-token"))


def test_oidc_rejects_cross_tenant_claim() -> None:
    authenticator = OIDCAuthenticator(enabled=True, token_validator=lambda token: {"tenant_id": "tenant-b"})
    try:
        authenticator.authorize_tenant(_request("Bearer valid-token"), "tenant-a")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
    else:
        raise AssertionError("expected 403")


def test_hybrid_mode_falls_back_to_api_key() -> None:
    fallback = ApiKeyAuthenticator(enabled=True, tenant_keys={"key-a": "tenant-a"})
    authenticator = OIDCAuthenticator(enabled=True, token_validator=lambda token: {}, fallback=fallback)
    request = Request({"type": "http", "headers": [(b"x-api-key", b"key-a")]})
    authenticator.authorize_tenant(request, "tenant-a")
