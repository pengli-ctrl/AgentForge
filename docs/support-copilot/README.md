# Support Copilot MVP

## Goal

Build the first high-frequency AgentForge scenario: AI-assisted customer support and after-sales ticket handling.

The MVP proves that AI can reduce ticket handling time and improve response consistency while keeping all customer-facing and high-risk actions under human control.

## Non-Negotiable Boundaries

- AI may classify, retrieve, summarize, and draft.
- AI must not send customer replies automatically in the MVP.
- Refund, compensation, privacy, account-lock, contract, and complaint escalation actions require approval.
- Every action must have tenant, task, trace, policy, model, and cost attribution.
- Existing business systems remain the source of truth.

## Primary User Flow

1. A message or ticket event enters through Feishu or a generic webhook.
2. The system validates signature, tenant, and idempotency key.
3. A ticket is created if it does not already exist.
4. The system classifies intent, priority, product, and owning team.
5. Customer context and knowledge are retrieved.
6. A reply draft and recommended action are generated.
7. Risk and confidence are evaluated.
8. Low-risk drafts are saved for agent review; high-risk drafts wait for supervisor approval.
9. An agent accepts, edits, rejects, or escalates the draft.
10. The approved result is written back to the ticket system.
11. Feedback, cost, trace, and audit events are recorded.

## MVP Metrics

- First response time reduction.
- Human handling time reduction.
- Draft acceptance rate.
- Classification accuracy.
- Citation correctness.
- High-risk approval coverage.
- Cost per ticket.

## MVP Stack

- FastAPI
- Temporal Python SDK
- PostgreSQL + Alembic
- Valkey
- LiteLLM
- PostgreSQL FTS + pgvector
- MinIO/S3
- OpenTelemetry + Langfuse
- Next.js admin console
- Feishu connector first

## Delivery Order

1. Domain model and ticket state machine.
2. Temporal workflow and idempotency.
3. Feishu/webhook ingestion and ticket creation.
4. Classification and retrieval.
5. Reply drafting and risk assessment.
6. Approval and write-back.
7. Observability, evaluation, and admin console.
8. Pilot and ROI report.

