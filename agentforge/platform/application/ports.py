from __future__ import annotations

from typing import Protocol

from agentforge.platform.domain.audit import AuditEvent
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
from agentforge.platform.domain.regression import GoldenItem, QualityReport, RegressionRun
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
