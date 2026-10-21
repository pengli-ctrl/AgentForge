# AgentForge 3.1.0 Release Notes

Release date: 2026-10-21

## Highlights

AgentForge 3.1.0 delivers the current commercial delivery baseline:

- tenant-level module configuration and governance;
- module SDK, runnable template and third-party contract suite;
- PostgreSQL/Temporal/MinIO/Valkey integration and Outbox reliability;
- Secret, PII, audit retention and private Helm delivery;
- SaaS tenant lifecycle, plans, metering, alerts, billing and operations.

## Compatibility

- Python: 3.10, 3.11, 3.12
- PostgreSQL: 15+ (17 recommended)
- Temporal: 1.32+
- Valkey/Redis: 7+
- MinIO/S3 compatible object storage
- Migration target: `20261021_0032`
- Previous commercial migration baseline: `20261020_0028`

No intentional public API removals. Existing tenants without a `tenant_accounts` record remain active for backward compatibility.

## Operational notes

- Production authentication remains fail-closed. Configure API keys before deployment.
- OIDC is an extension point in this release; a production IdP adapter still requires customer-specific configuration.
- Real infrastructure tests require Docker and `AGENTFORGE_RUN_INFRA_TESTS=1`.
- Helm chart references an existing Secret; secrets are not stored in chart values.
