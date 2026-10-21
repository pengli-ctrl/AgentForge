# Changelog

All notable changes to AgentForge are documented in this file.

## [3.1.0] - 2026-10-21

### Added

- Tenant-level versioned module configuration with deployment defaults, tenant overrides, optimistic version checks, Audit and Outbox.
- Module SDK, runnable module template, Demo Asset module, `agentforge.modules` entry-point discovery, reusable module contract suite and deprecation policy.
- PostgreSQL, Temporal, MinIO/S3 and Valkey integration test suite with Docker Compose and CI entry point.
- Outbox handler receipts for idempotent handler execution, failed/dead-letter replay and publisher retry.
- Secret resolver for environment, Vault, KMS and generic secret references.
- OIDC/SSO provider extension point and tenant/permission checks.
- Recursive Audit output redaction, tenant audit retention purge and PII lifecycle erasure service.
- Helm private-deployment chart, security checklist, backup/restore/upgrade/rollback runbook.
- SaaS tenant lifecycle, plan catalog, usage metering, quota alerts, overage policies, billing adapter and operations overview.
- Automatic metering adapters for model tokens, OCR pages, Temporal workflows, object storage and notifications.
- Release verification, deterministic private package builder and security scan entry points.

### Changed

- Unified package, API, module platform, Helm chart and image versions to `3.1.0`.
- Root Docker image now starts the platform application and checks `/health/live`.
- Docker runtime uses a non-root user.
- Aligned Markdown documentation with the current module layout, infrastructure, SaaS control plane and private-delivery workflow; removed historical planning and test-record documents that are not part of the product documentation.

### Security

- Module configuration rejects plaintext sensitive values and validates `secret_refs`.
- Attachment download URLs are bounded to 1-3600 seconds.
- Suspended and cancelled tenants fail closed at module API boundaries.
- Outbox handler retries no longer repeat already successful business handlers.
- Audit export redacts Bearer tokens, emails, phone numbers and identity-card numbers by default.

### Database migrations

- `20261021_0029_tenant_module_config`
- `20261021_0030_demo_asset`
- `20261021_0031_outbox_handler_receipts`
- `20261021_0032_saas_control_plane`

Upgrade target: `20261021_0032`. Previous commercial baseline: `20261020_0028`.

## [3.0.0] - 2026-10-20

- Shared platform kernel with Support and Expense modules.
- Tenant module enablement, SLA notifications, invoice gates, connector writeback and expense automation.
