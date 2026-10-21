# AgentForge

![CI](https://img.shields.io/badge/CI-passing-brightgreen)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Tests](https://img.shields.io/badge/Tests-884%20passed-brightgreen)
![Version](https://img.shields.io/badge/version-3.1.0-blue)

> **Move AI from demos into real business workflows without giving up governance, reliability, or delivery control.**

AgentForge is an enterprise AI platform built around a **shared kernel, composable business modules, and SaaS/private-delivery packaging**. It brings model access, agent orchestration, RAG, policy, approval, audit, quotas and cost, durable workflows, and connectors into one foundation. Business teams implement only their domain module and get a governed, measurable, operable, and deliverable AI product.

Current version: `3.1.0`. Implemented modules: **Support**, **Expense**, and **Demo Asset**.

### At a glance

| Problem | What AgentForge provides |
|---|---|
| Put AI into real workflows | DAG orchestration, agents, tools, RAG, model routing, and semantic cache |
| Make AI enterprise-safe | Multi-tenancy, RBAC, policy, approval, audit, secret references, and fail-closed defaults |
| Share one platform across businesses | `ModuleManifest`, `ModuleRuntime`, SDK ports, and `ModuleRegistry` |
| Control usage and cost | Quotas, token cost, plans, metering, overage policies, alerts, and invoices |
| Survive long-running failures | Temporal, schedules, task queues, Outbox, DLQ, replay, and idempotent handlers |

### Who is it for?

- **AI platform and architecture teams** building a shared foundation for models, agents, RAG, governance, and cost.
- **Enterprise SaaS product teams** turning support, finance, or operations workflows into AI-powered products.
- **Solution and private-delivery teams** shipping the same code as SaaS or customer-hosted deployments.
- **Backend and agent engineers** adding modules through the SDK while reusing tools, memory, Temporal, Outbox, and connectors.
- **Security and operations teams** applying fail-closed auth, audit, policy, quotas, DLQ, hardened containers, and production checks.

> AgentForge is intentionally heavier than a one-off prompt demo. It is for teams turning AI into a reusable, governed, and commercially deliverable platform.

### What can you build?

- **Support copilot**: intake → classification → retrieval → reply draft → human review → write-back → SLA and notification.
- **Expense automation**: OCR → field confirmation → policy checks → approval → invoice gates → ledger → finance write-back.
- **Custom industry modules**: inventory, contracts, procurement, logistics, or other domains through the module SDK.
- **Multi-tenant SaaS**: plan-based module enablement, usage metering, alerts, and invoices.
- **Private delivery**: Helm deployment of API, workers, Outbox worker, and migrations against customer infrastructure.

---

## Core capabilities

| Domain | Capabilities | Value |
|---|---|---|
| **Agent runtime and orchestration** | Agents, three-tier memory, tools, context, DAG, Planner, LoopBlock, timeout, degradation, and guards | Complex AI flows with controlled concurrency, failure, and cost |
| **Model and knowledge gateway** | Routing, semantic cache, token cost, tracing, hybrid retrieval, reranking, and hallucination guards | One cost-aware interface for models and knowledge |
| **Enterprise governance** | Tenancy, RBAC, policy, approval, audit, redaction, retention, and PII lifecycle | AI inside enterprise permission and accountability boundaries |
| **Reliable workflows** | Temporal, schedules, task queues, Outbox, Kafka, receipts, DLQ, connectors, and webhook HMAC | Durable, auditable, retryable, and compensatable side effects |
| **Business module platform** | Manifest, SDK ports, entry points, dual repositories, tenant config, contract tests, and versioning | One kernel, multiple independently deliverable businesses |
| **SaaS and private delivery** | Tenant lifecycle, plans, metering, billing, operations, Helm, secrets, and migrations | A commercial delivery baseline from day one |

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Access: REST / Webhook / Feishu / OpenAPI Connector / CLI / SDK     │
├─────────────────────────────────────────────────────────────────────┤
│ Business modules: Support / Expense / Demo Asset / Custom modules   │
│ Layers: api · application · domain · infrastructure · workflows     │
├─────────────────────────────────────────────────────────────────────┤
│ Governance: Tenant · RBAC · Policy · Approval · Audit · Quota       │
│             SaaS · Module Config · Connector · Secret              │
├──────────────────────────────────┬──────────────────────────────────┤
│ Agent runtime and orchestration  │ Model and knowledge gateway      │
│ Agent / Memory / Tool / Context  │ Router / Cache / RAG / Cost      │
│ DAG / Planner / LoopBlock        │ Trace / Reranker / Guard         │
├──────────────────────────────────┴──────────────────────────────────┤
│ Reliable delivery: Temporal · Outbox/Kafka · DLQ · Schedule         │
├─────────────────────────────────────────────────────────────────────┤
│ Data and observability: PostgreSQL/pgvector · S3 · Valkey · OTel    │
└─────────────────────────────────────────────────────────────────────┘
```

### Request path

```text
User / external system
  -> authentication, tenant state, module enablement
  -> module API and domain use case
  -> orchestration, RAG, model gateway, tools, and connectors
  -> policy and approval for high-risk actions
  -> audit, Outbox, Temporal, cost, and usage records
  -> response plus durable asynchronous work
```

### Design principles

- **Govern once**: tenancy, authorization, audit, quota, cost, and observability live in the shared kernel.
- **Isolate domains**: platform core does not import concrete modules.
- **Reliability by design**: business writes, Outbox, Temporal, idempotency, and DLQ are designed together.
- **One codebase, two deliveries**: SaaS and private Helm packaging share the same platform code.
- **Secure by default**: fail-closed auth, secret references, and approval for high-risk actions.

## Project status

AgentForge `3.1.0` is a **runnable, testable, extensible, and privately deliverable commercial baseline**:

- shared kernel, module SDK, tenant module configuration, and three business modules;
- SaaS lifecycle, plans, metering, invoices, and operations control plane;
- Temporal, Outbox, DLQ, object storage, Valkey, and real infrastructure tests;
- security baseline, audit redaction, PII lifecycle, Helm, and runbooks;
- offline baseline: **884 passed, 7 skipped**, including **418 platform tests**.

Production rollout still requires environment-specific validation of IdP/SSO, Vault/KMS, WAF/DLP, highly available data services, image CVE/SBOM scanning, and Kubernetes install, upgrade, rollback, and disaster-recovery drills.

---
## Repository layout

```text
AgentForge/
├── agentforge/
│   ├── agents/
│   ├── api/
│   ├── cli/
│   ├── core/
│   ├── gateway/
│   ├── llm/
│   ├── observability/
│   ├── orchestration/
│   ├── prompts/
│   ├── rag/
│   ├── safety/
│   ├── sdk/
│   ├── storage/
│   ├── tools/
│   ├── workflow/
│   └── platform/
│       ├── api/
│       ├── application/
│       ├── cli/
│       ├── connectors/
│       ├── core/
│       ├── domain/
│       ├── infrastructure/
│       ├── modules/
│       │   ├── support/
│       │   │   ├── api/
│       │   │   ├── application/
│       │   │   ├── connectors/
│       │   │   ├── domain/
│       │   │   ├── infrastructure/
│       │   │   ├── workflows/
│       │   │   ├── config.py
│       │   │   ├── module.py
│       │   │   ├── ports.py
│       │   │   ├── runtime.py
│       │   │   └── README.md
│       │   ├── expense/
│       │   │   ├── api/
│       │   │   ├── application/
│       │   │   ├── domain/
│       │   │   ├── infrastructure/
│       │   │   ├── workflows/
│       │   │   ├── config.py
│       │   │   ├── module.py
│       │   │   ├── ports.py
│       │   │   ├── runtime.py
│       │   │   └── README.md
│       │   └── demo_asset/
│       │       ├── api/
│       │       ├── application/
│       │       ├── domain/
│       │       ├── infrastructure/
│       │       ├── workflows/
│       │       ├── config.py
│       │       ├── module.py
│       │       ├── ports.py
│       │       └── README.md
│       ├── observability/
│       ├── sdk/
│       ├── security/
│       ├── workflows/
│       └── runtime.py
├── bench/
├── configs/
│   ├── dev/
│   ├── prod/
│   ├── workflows/
│   └── logging.yaml
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── platform/
│   └── infra/
├── docs/
│   ├── architecture.md
│   ├── commercial/
│   ├── infrastructure/
│   ├── modules/
│   ├── release/
│   └── security/
├── alembic/
│   └── versions/
├── deploy/
│   ├── grafana/
│   ├── helm/agentforge/
│   │   ├── templates/
│   │   ├── Chart.yaml
│   │   └── values.yaml
│   └── platform/
├── templates/module-template/
├── examples/
├── migrations/
├── scripts/
├── requirements/
├── .github/
├── CHANGELOG.md
├── CONTRIBUTING.md
├── README.md
├── README.en.md
├── SECURITY.md
├── Makefile
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

---

## Quick start

Install:

```bash
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate        # Windows
pip install -r requirements-dev.txt
pip install -e .
```

Start the complete platform stack:

```bash
make platform-up
```

The API listens on `http://localhost:8000` and exposes `/health/live` and `/health/ready`. These are process-level probes; dependency health must be checked through service logs and infrastructure monitoring.

Start local dependencies only:

```bash
make platform-lite-up
```

This is equivalent to:

```bash
docker compose -f deploy/platform/docker-compose.lite.yml up -d
```

The complete Compose profile includes PostgreSQL, Valkey, Temporal, MinIO, Kafka, OTel Collector, API, Worker, and Outbox Worker. See [deploy/platform/README.md](deploy/platform/README.md).

Authentication is fail-closed by default. In production, configure keys before startup:

```bash
export AGENTFORGE_ADMIN_API_KEY='replace-with-a-strong-secret'
export AGENTFORGE_API_KEYS='{"replace-with-tenant-key":"tenant-a"}'
```

`AGENTFORGE_ALLOW_NO_AUTH=true` exists only for explicit local development and must never be used for publicly exposed environments.

Module enablement:

```bash
AGENTFORGE_ENABLED_MODULES=support
AGENTFORGE_ENABLED_MODULES=expense
AGENTFORGE_ENABLED_MODULES=support,expense
```

The default is `support,expense`. The `asset` reference module is enabled through plugin or test assembly.

Private deployment:

```bash
kubectl create namespace agentforge
helm upgrade --install agentforge deploy/helm/agentforge \
  -n agentforge \
  --set image.repository=registry.example.com/agentforge \
  --set image.tag=3.1.0 \
  --set existingSecret=agentforge-secrets
```

See the [private deployment runbook](docs/security/PRIVATE_DEPLOYMENT_RUNBOOK.md) for production installation, backup, restore, upgrade, and rollback.

---

## Platform APIs

| Prefix | Capability |
|---|---|
| `/v1/support` | Support tickets and compatibility routes |
| `/v1/expense` | Claims, OCR, attachments, approval, ledger, invoice gates |
| `/v1/assets` | Demo Asset reference module (manifest prefix) |
| `/v1/console` | Operations console and approval inbox |
| `/v1/rbac` | Roles, permissions, and assignments |
| `/v1/authorize` | Declarative authorization decisions |
| `/v1/policies` | Declarative policy inspection and reload |
| `/v1/quotas` | Tenant quota management |
| `/v1/audit` | Audit query, export, and retention |
| `/v1/costs` | Cost and model distribution |
| `/v1/knowledge` | Knowledge ingestion and hybrid retrieval |
| `/v1/evaluations` | Retrieval and classification evaluation |
| `/v1/regression` | Golden datasets and offline regression |
| `/v1/release` | Prompt/model version release and quality gates |
| `/v1/connectors` | Connector registry and management |
| `/v1/outbox` | Outbox, DLQ, replay, and discard |
| `/v1/admin/*` | Tenant lifecycle, plans, usage, invoices, operations |

See [SaaS control plane](docs/commercial/SAAS_CONTROL_PLANE.md) for tenant and billing APIs.

---

## Development and tests

```bash
make format
make lint
make type-check
make test
make test-unit
make test-integration
python -m pytest tests/platform -q
```

Run real infrastructure tests:

```bash
make test-infra
# Windows PowerShell
./scripts/run_infra_tests.ps1
```

The infrastructure runner starts `docker-compose.lite.yml`, creates test databases, runs `tests/infra`, and executes a migration drill. Tests skip real services unless `AGENTFORGE_RUN_INFRA_TESTS=1` is set.

Release validation:

```bash
make release-check
python scripts/security_scan.py
```

See [production infrastructure integration](docs/infrastructure/PRODUCTION_INTEGRATION.md) for details.

---

## Documentation

| Document | Purpose |
|---|---|
| [Architecture](docs/architecture.md) | Current layers, module boundaries, data paths, and deployment modes |
| [Module integration](docs/modules/MODULE_INTEGRATION_GUIDE.md) | Module contract, tenant isolation, and acceptance |
| [Versioning and deprecation](docs/modules/VERSIONING_AND_DEPRECATION.md) | Compatibility and release policy |
| [Support module](agentforge/platform/modules/support/README.md) | Tickets, SLA, review, notifications, and write-back |
| [Expense module](agentforge/platform/modules/expense/README.md) | Claims, OCR, approval, invoice gates, and ledger |
| [Demo Asset module](agentforge/platform/modules/demo_asset/README.md) | Third-party module reference implementation |
| [Module template](templates/module-template/README.md) | Runnable module template |
| [SaaS control plane](docs/commercial/SAAS_CONTROL_PLANE.md) | Lifecycle, plans, metering, and billing |
| [Infrastructure integration](docs/infrastructure/PRODUCTION_INTEGRATION.md) | PostgreSQL, Temporal, MinIO, Valkey, and Outbox |
| [Private deployment runbook](docs/security/PRIVATE_DEPLOYMENT_RUNBOOK.md) | Helm operations and disaster recovery |
| [Security checklist](docs/security/SECURITY_CHECKLIST.md) | Implemented controls and field acceptance items |
| [Migration guide](docs/release/MIGRATION_GUIDE_3.1.0.md) | Upgrade to 3.1.0 |
| [Release notes](docs/release/RELEASE_NOTES_3.1.0.md) | 3.1.0 capabilities and compatibility |

---

## Technology stack

- Python 3.10+, FastAPI, Pydantic 2, async SQLAlchemy 2
- PostgreSQL 15+, Alembic, pgvector, full-text search
- Temporal 1.32+, transactional Outbox, Kafka
- Valkey/Redis 7+, MinIO/S3
- OpenTelemetry, Prometheus, Grafana
- Docker Compose and Helm
- Feishu, HMAC-signed webhooks, and OpenAPI connectors

---

## Security

- Authentication is fail-closed in production.
- Secret references support `env://`, `vault://`, `kms://`, and `secret://`; plaintext sensitive module configuration is rejected.
- Audit export recursively redacts bearer tokens, email addresses, phone numbers, and identity-card numbers by default.
- Attachment download URLs are bounded to 1-3600 seconds and default to 300 seconds.
- Private containers run as non-root with a read-only root filesystem and all Linux capabilities dropped.
- Report vulnerabilities according to [SECURITY.md](SECURITY.md).

---

## Known boundaries

- OIDC provides the provider Port, principal model, and tenant/permission checks; customer IdP discovery, JWKS, and group-claim mapping still require deployment-specific integration.
- Vault/KMS providers and rotation interfaces exist, but production key custody, rotation, and key policy require field acceptance.
- The Helm chart expects external PostgreSQL, Temporal, MinIO, and Valkey services.
- Compose is intended for local development, demos, and integration testing, not highly available production.
- Department/project-level budgets and incremental materialization of invoice-gate metrics are not implemented.

---

## License

[MIT License](LICENSE) © 2024 Li Peng
