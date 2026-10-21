# Security Policy

## Supported Versions

AgentForge 3.x is the supported release line.

| Version | Supported |
|---|---|
| 3.x | Yes |
| 2.x | No (EOL) |
| 1.x | No (EOL) |

## Reporting a Vulnerability

Do not open a public issue for a suspected vulnerability.

Send a private report to **pl2847253@gmail.com** with:

- affected version and deployment mode;
- description and potential impact;
- reproduction steps or proof of concept;
- relevant logs with secrets and PII removed;
- suggested mitigation, if known.

Acknowledgement target: 48 hours. Critical fixes target: 7 days. High-severity fixes target: 14 days. Other issues are handled according to severity and release risk.

## Security Model

### Authentication and authorization

- API authentication is fail-closed by default.
- Production startup fails when no admin or tenant API key is configured.
- API keys are bound to tenants and compared using constant-time comparison.
- Admin and tenant keys have separate privileges.
- RBAC, declarative policy, tenant/module access, and high-risk approval checks apply at API and application boundaries.
- OIDC provides a provider extension point and tenant/permission checks; production IdP integration must be configured per customer.

### Tenant isolation

- Tenant and module data access must explicitly include `tenant_id`.
- Module API boundaries reject suspended and cancelled tenants.
- Cross-tenant list/get operations return empty, 404, or 403 as appropriate.
- Audit, Outbox, quota, cost, caches, and events are tenant-scoped.

### Secrets

- Never commit API keys, database passwords, webhook secrets, Vault tokens, or KMS credentials.
- Module configuration must use `secret_refs`, not plaintext secrets.
- Supported schemes are `env://`, `vault://`, `kms://`, and `secret://`.
- `SecretValue.reveal()` is the explicit access boundary; string representations redact content.
- The Helm chart references an existing Kubernetes Secret and does not store secrets in values.
- Rotate credentials periodically and after any suspected exposure.

### Data protection

- Audit export redacts bearer tokens, email addresses, phone numbers, and identity-card numbers by default.
- Audit retention purge and PII erasure are tenant-scoped and audited.
- Attachment download URLs are bounded to 1-3600 seconds.
- Production data stores should use encryption at rest, TLS in transit, and least-privilege credentials.
- Backups must be encrypted, access-controlled, tested for restore, and retained according to policy.

### Network and connector security

- Deploy behind TLS termination and restrict administrative endpoints to trusted networks.
- Do not expose PostgreSQL, Temporal, MinIO, Valkey, or Kafka ports publicly.
- Use network policies and firewall rules between application and infrastructure networks.
- Webhook endpoints use HMAC and/or provider signature verification.
- Connector credentials must come from a secret manager and use least-privilege accounts.
- Apply WAF, DLP, IP allow-lists, and egress controls where required by the deployment environment.

### Container and Kubernetes security

- Private deployment containers run as non-root.
- Use a read-only root filesystem, disable privilege escalation, and drop Linux capabilities.
- Use Kubernetes Secrets or an external secret manager, not ConfigMaps, for credentials.
- Run the migration Job before rolling out API and workers.
- Enforce Pod Security, resource quotas, network policies, TLS, and image admission controls.
- Scan images for vulnerabilities and produce an SBOM before production release.

## Deployment Boundary

AgentForge is a commercial baseline, not a production-certified platform. The controls above describe implemented defaults and extension points. See [Security Design](docs/security/SECURITY_DESIGN.md) for the detailed control model and explicit boundaries.

Before using the project in a real customer environment, the delivery team must separately complete and verify:

- real IdP discovery, JWKS validation, and group claim mapping;
- Vault/KMS custody, rotation, and disaster recovery;
- WAF/DLP, network policy, and egress controls;
- high availability and capacity validation for external middleware;
- Kubernetes installation, upgrade, rollback, backup, and restore drills;
- image and dependency vulnerability scanning.