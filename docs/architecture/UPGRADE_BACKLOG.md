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
