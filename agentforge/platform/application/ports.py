from __future__ import annotations

import builtins
from datetime import datetime
from typing import Protocol

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.connector import ConnectorSpec
from agentforge.platform.domain.cost import CostRecord
from agentforge.platform.domain.evaluation import EvaluationSample
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    RetrievedChunk,
    SearchMode,
)
from agentforge.platform.domain.model import ModelRequest, ModelResponse
from agentforge.platform.domain.rbac import Role, RoleAssignment
from agentforge.platform.domain.regression import GoldenItem, QualityReport, RegressionRun
from agentforge.platform.domain.reporting import ReportRun, ScheduledReport
from agentforge.platform.domain.tenant_quota import TenantQuota
from agentforge.platform.domain.ticket import Ticket


class TicketRepository(Protocol):
    async def get(self, tenant_id: str, ticket_id: str) -> Ticket | None: ...

    async def save(
        self,
        ticket: Ticket,
        events: list[EventEnvelope] | None = None,
    ) -> Ticket: ...

    async def get_by_idempotency_key(
        self, tenant_id: str, idempotency_key: str
    ) -> Ticket | None: ...

    async def list(
        self,
        tenant_id: str,
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[Ticket], str | None]: ...


class KnowledgeRepository(Protocol):
    async def save_document(
        self,
        document: KnowledgeDocument,
        chunks: list[KnowledgeChunk],
    ) -> None: ...

    async def search(
        self,
        tenant_id: str,
        query: str,
        limit: int = 5,
        mode: SearchMode = "hybrid",
        fts_weight: float = 0.5,
        vector_weight: float = 0.5,
    ) -> list[RetrievedChunk]: ...

    async def backfill_embeddings(self, tenant_id: str | None = None) -> int: ...


class CostRepository(Protocol):
    async def save(self, record: CostRecord) -> None: ...

    async def total_for_tenant(self, tenant_id: str) -> float: ...

    async def summary_for_tenant(self, tenant_id: str) -> dict: ...

    async def list_tenants(self) -> list[str]: ...

    async def daily_summary(
        self,
        tenant_id: str,
        days: int = 30,
    ) -> list[dict]: ...


class EventPublisher(Protocol):
    async def publish(self, event: EventEnvelope) -> None: ...


class ModelGateway(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse: ...


class VectorStore(Protocol):
    async def search(self, tenant_id: str, query: str, limit: int = 5) -> list[dict]: ...


class ReplyConnector(Protocol):
    async def send_text(
        self,
        target: str,
        text: str,
        idempotency_key: str,
    ) -> dict: ...


class AuditRepository(Protocol):
    async def save(self, event: AuditEvent) -> None: ...

    async def list_events(
        self,
        tenant_id: str,
        limit: int = 100,
        resource_id: str | None = None,
    ) -> list[AuditEvent]: ...

    async def query_events(
        self,
        tenant_id: str | None = None,
        action: str | None = None,
        actor_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[AuditEvent], str | None]: ...


class EvaluationRepository(Protocol):
    async def save(self, sample: EvaluationSample) -> None: ...

    async def list_samples(
        self,
        tenant_id: str,
        limit: int = 100,
        action: str | None = None,
    ) -> list[EvaluationSample]: ...

    async def summary(self, tenant_id: str) -> dict: ...


class RegressionRepository(Protocol):
    """Golden Dataset 离线回归样本与运行记录的持久化仓库。"""

    async def save_golden(self, item: GoldenItem) -> None: ...

    async def list_golden(
        self,
        tenant_id: str,
        limit: int = 100,
    ) -> list[GoldenItem]: ...

    async def save_run(self, run: RegressionRun) -> None: ...

    async def save_report(self, report: QualityReport) -> None: ...

    async def get_run(self, run_id: str) -> RegressionRun | None: ...

    async def list_runs(self, tenant_id: str, limit: int = 100) -> list[RegressionRun]: ...


class ConnectorRepository(Protocol):
    """Persists connector registration specs (memory / sqlalchemy dual impl).

    Specs hold credential references and connection config but no secrets, so
    they are safe to store in a plain table. Adapter instances themselves are
    not serialized; they are re-bound at runtime from the persisted spec.
    """

    async def save_spec(self, spec: ConnectorSpec) -> None: ...

    async def get_spec(self, connector_id: str) -> ConnectorSpec | None: ...

    async def list_specs(
        self,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[ConnectorSpec]: ...

    async def delete_spec(self, connector_id: str) -> None: ...


class RbacRepository(Protocol):
    """Persists RBAC roles and user-role assignments (memory / sqlalchemy)."""

    async def save_role(self, role: Role) -> None: ...

    async def get_role(self, tenant_id: str, role_id: str) -> Role | None: ...

    async def list_roles(self, tenant_id: str) -> list[Role]: ...

    async def save_assignment(self, assignment: RoleAssignment) -> None: ...

    async def list_assignments(self, tenant_id: str) -> list[RoleAssignment]: ...

    async def assignments_for_user(
        self,
        tenant_id: str,
        user_id: str,
    ) -> list[RoleAssignment]: ...


class TenantQuotaRepository(Protocol):
    """Persists per-tenant quota (memory / sqlalchemy dual impl)."""

    async def upsert(self, quota: TenantQuota) -> None: ...

    async def get(self, tenant_id: str) -> TenantQuota | None: ...

    async def list(self, limit: int = 100) -> list[TenantQuota]: ...

    async def delete(self, tenant_id: str) -> None: ...


class ScheduledReportRepository(Protocol):
    """Persists recurring operational report schedules (memory / sqlalchemy)."""

    async def save(self, report: ScheduledReport) -> None: ...

    async def get(self, report_id: str) -> ScheduledReport | None: ...

    async def list_schedules(
        self, tenant_id: str | None = None, limit: int = 100
    ) -> list[ScheduledReport]: ...

    async def delete(self, report_id: str) -> None: ...

    async def list_due(
        self,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[ScheduledReport]: ...


class ReportRunRepository(Protocol):
    """Persists materialized operational report runs (memory / sqlalchemy)."""

    async def save(self, run: ReportRun) -> None: ...

    async def get(self, run_id: str) -> ReportRun | None: ...

    async def list(
        self,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
        archived: bool | None = None,
    ) -> list[ReportRun]: ...

    async def list_page(
        self,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
        archived: bool | None = None,
        cursor: str | None = None,
    ) -> tuple[builtins.list[ReportRun], str | None]: ...

    async def set_archived(self, run_id: str, archived: bool) -> None: ...

    async def delete_older_than(
        self,
        cutoff: datetime,
        tenant_id: str | None = None,
        include_archived: bool = False,
    ) -> int: ...
