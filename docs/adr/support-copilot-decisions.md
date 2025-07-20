# Support Copilot Architecture Decisions

## ADR-001: Modular Monolith Before Microservices

**Decision:** Start with one deployable application plus separate worker processes.

**Reason:** The first milestone must prove the business flow and reliability. Splitting into independent services now would add networking, deployment, tracing, and schema coordination costs before product-market validation.

**Consequences:** Modules must have explicit boundaries and ports so the workflow, connector, policy, and RAG components can be extracted later.

## ADR-002: Temporal for Durable Execution

**Decision:** Use Temporal Python SDK for ticket workflows.

**Reason:** Support workflows can wait for human approval and may run for hours or days. Temporal provides durable state, retries, timers, signals, queries, and recovery.

**Consequences:** Workflow code must be deterministic. External I/O must live in Activities. Workflow changes require versioning.

## ADR-003: PostgreSQL Outbox Before Kafka

**Decision:** Persist domain events in PostgreSQL Outbox and publish them through a worker. Keep a Kafka-compatible publisher interface.

**Reason:** The MVP still needs reliable event delivery, but Kafka adds operational cost. Outbox provides the correct consistency model while keeping a migration path.

**Consequences:** Consumers must be idempotent. The publisher must support retry, ordering per aggregate, and DLQ before Kafka is introduced.

## ADR-004: LiteLLM Behind a Model Gateway Port

**Decision:** Use LiteLLM as the provider adapter and expose an internal `ModelGateway` interface.

**Reason:** Provider protocol maintenance is not a differentiator. AgentForge should own task routing, quotas, policies, prompt versions, and cost attribution.

**Consequences:** No business service may call a model provider directly. Cost and model metadata are recorded in the application.

## ADR-005: pgvector First, Qdrant When Scale Requires It

**Decision:** Use PostgreSQL FTS plus pgvector for the MVP. Keep a `VectorStore` port for Qdrant.

**Reason:** A single PostgreSQL dependency is easier to operate and keeps ticket metadata, permissions, knowledge versions, and vectors transactionally close.

**Consequences:** Qdrant migration must be driven by measured limits, not anticipated scale.

## ADR-006: Human Approval for Customer-Facing Actions

**Decision:** The MVP stores reply drafts but never sends them automatically.

**Reason:** Trust, compliance, and evaluation quality are more important than demonstrating full automation.

**Consequences:** The workflow includes an approval wait state. High-risk actions cannot bypass the policy engine.

