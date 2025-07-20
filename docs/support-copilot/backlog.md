# Support Copilot Delivery Backlog

Priority:

- P0: required to prove the MVP.
- P1: required before a real pilot.
- P2: required before productization.

## E1. Domain and Persistence

- P0 SC-101 Define Ticket, Message, Customer, Tenant, and AgentRun models.
- P0 SC-102 Implement ticket state transitions and invariants.
- P0 SC-103 Add tenant-scoped repository interfaces.
- P0 SC-104 Add PostgreSQL schema and Alembic migration.
- P0 SC-105 Add idempotency key uniqueness and conflict handling.
- P0 SC-106 Add audit event model.
- P1 SC-107 Add row-level security policy.
- P1 SC-108 Add retention and deletion policy.

## E2. Durable Runtime

- P0 SC-201 Integrate Temporal Python SDK.
- P0 SC-202 Implement SupportTicketWorkflow.
- P0 SC-203 Implement intake, classify, retrieve, draft, risk, approval, publish activities.
- P0 SC-204 Add retry policy, timeout policy, cancellation, and query.
- P0 SC-205 Add approval signal and wait condition.
- P0 SC-206 Add worker queues for read, write, model, RAG, and connector work.
- P0 SC-207 Add process-restart recovery test.
- P1 SC-208 Add Temporal workflow versioning policy.

## E3. Ingestion and Connector

- P0 SC-301 Add generic signed webhook endpoint.
- P0 SC-302 Add Feishu test app event adapter.
- P0 SC-303 Add connector interface and credential reference model.
- P0 SC-304 Add duplicate message suppression.
- P0 SC-305 Add ticket lookup and creation.
- P1 SC-306 Add Feishu card approval.
- P2 SC-307 Add WeCom, DingTalk, email, and CRM adapters.

## E4. Classification and Retrieval

- P0 SC-401 Implement structured classification schema.
- P0 SC-402 Add intent, priority, product, and team classifier.
- P0 SC-403 Add knowledge ingestion and chunk metadata.
- P0 SC-404 Add PostgreSQL FTS retrieval.
- P0 SC-405 Add pgvector retrieval adapter.
- P0 SC-406 Add hybrid result merge and reranking.
- P0 SC-407 Require citation references for factual output.
- P0 SC-408 Add classification and retrieval evaluation.

## E5. Reply Draft and Risk

- P0 SC-501 Implement reply draft schema.
- P0 SC-502 Add prompt and model version metadata.
- P0 SC-503 Add suggested action and confidence.
- P0 SC-504 Add high-risk keyword and policy checks.
- P0 SC-505 Add no-citation and low-confidence fallback.
- P1 SC-506 Add prompt registry and rollback.
- P1 SC-507 Add human feedback capture.

## E6. Approval, Write-Back and Audit

- P0 SC-601 Add approval task model and state machine.
- P0 SC-602 Add internal approval API.
- P0 SC-603 Block customer-facing send without approval.
- P0 SC-604 Add write-back adapter with idempotency key.
- P0 SC-605 Add audit trail for approval, edit, rejection, and publish.
- P1 SC-606 Add Feishu card approval callback.
- P1 SC-607 Add compensation or manual recovery flow.

## E7. Model Gateway, Cost and Evaluation

- P0 SC-701 Wrap LiteLLM behind ModelGateway interface.
- P0 SC-702 Add tenant and task cost attribution.
- P0 SC-703 Add model timeout, retry, and fallback policy.
- P0 SC-704 Add token and cost records.
- P0 SC-705 Add Golden Dataset runner.
- P1 SC-706 Add budget and concurrency quota.
- P1 SC-707 Add Langfuse trace export.

## E8. Admin Console, Deployment and Operations

- P0 SC-801 Add Docker Compose Lite infrastructure.
- P0 SC-802 Add health and readiness endpoints.
- P0 SC-803 Add task status and approval inbox API.
- P1 SC-804 Add Next.js task and approval console.
- P1 SC-805 Add Prometheus metrics and OpenTelemetry exporter.
- P1 SC-806 Add DLQ retry tool.
- P1 SC-807 Add backup and restore runbook.
- P2 SC-808 Add Kubernetes and Helm deployment.

## First Two Weeks

1. Complete SC-101 through SC-106.
2. Complete SC-201 through SC-204.
3. Complete SC-301 through SC-305.
4. Complete SC-801 and SC-802.
5. Create an end-to-end test where a webhook creates a ticket and the workflow reaches `waiting_review`.

