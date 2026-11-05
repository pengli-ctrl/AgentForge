# Architecture Upgrade Backlog

> Each PR records residual work here. Resolve at the end of the nine-PR sequence.

## PR 0 - Baseline

- Added feature-flag settings and replacement ports.
- Remaining: wire each optional backend through composition root and add contract suites per backend.
- Remaining: verify settings against deployment values and document every environment variable.

## PR 1 - Envoy Gateway

- Added optional Gateway API templates and SSE metadata.
- Remaining: validate with a real Envoy Gateway controller and add TLS/canary route policies.
- Remaining: add staging smoke tests for SSE buffering, TLS, and tenant/version header routing.

## PR 2 - LiteLLM gateway

- Added configurable LiteLLM provider adapter and gateway factory.
- Remaining: add LiteLLM Proxy deployment values and shadow-routing comparison metrics.
- Remaining: validate 429/timeout/fallback behavior against a real proxy.

## PR 3 - OIDC authentication

- Added OIDC bearer adapter with API-key fallback and tenant/admin claim checks.
- Remaining: connect a JWKS/JWT validator and Keycloak staging configuration.
- Remaining: add token rotation, clock-skew, and IdP outage integration tests.

## PR 4 - OPA authorization

- Added injectable OPA adapter mapping policy decisions into the existing authorization domain.
- Remaining: add Rego policy package and wire `AUTHZ_ENGINE=opa` in the composition root.
- Remaining: add shadow comparison and fail-closed tests against a running OPA instance.

## PR 5 - Distributed rate limiting

- Added memory/Valkey backends on top of the existing atomic Valkey token-bucket primitive.
- Remaining: wire `RateLimitPort` into request middleware and Envoy rate-limit policy.
- Remaining: add multi-process concurrency and Redis-failure integration tests.
