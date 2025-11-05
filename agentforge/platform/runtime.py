from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.api.security import ApiKeyAuthenticator
from agentforge.platform.application.builtin_policies import (
    _async_relation_check,
    builtin_policies,
)
from agentforge.platform.application.classification_evaluation_service import (
    ClassificationEvaluationService,
)
from agentforge.platform.application.classifier import RuleBasedTicketClassifier
from agentforge.platform.application.connector_registry import ConnectorRegistry
from agentforge.platform.application.dashboard_service import DashboardService
from agentforge.platform.application.high_risk_authorizer import HighRiskActionAuthorizer
from agentforge.platform.application.knowledge_service import KnowledgeService
from agentforge.platform.application.model_router import ModelRouter
from agentforge.platform.application.openapi_adapter import build_openapi_adapter
from agentforge.platform.application.prompt_registry import PromptRegistry
from agentforge.platform.application.quality_gate_service import QualityGateService
from agentforge.platform.application.quota_service import QuotaAwareModelGateway
from agentforge.platform.application.regression_runner import RegressionRunner
from agentforge.platform.application.reply_draft_service import ReplyDraftService
from agentforge.platform.application.report_service import ReportService
from agentforge.platform.application.reranker import HybridReranker
from agentforge.platform.application.retrieval_evaluation_service import (
    RetrievalEvaluationService,
)
from agentforge.platform.application.routing_model_gateway import RoutingModelGateway
from agentforge.platform.application.support_ticket_processing_service import (
    SupportTicketProcessingService,
)
from agentforge.platform.application.support_ticket_service import SupportTicketService
from agentforge.platform.application.ticket_writeback import TicketWritebackService
from agentforge.platform.application.version_registry import ModelVersionRegistry
from agentforge.platform.domain.model import ModelProfile
from agentforge.platform.infrastructure.llm.litellm_gateway import LiteLLMModelGateway
from agentforge.platform.infrastructure.llm.static_gateway import StaticModelGateway
from agentforge.platform.infrastructure.memory_audit_repository import MemoryAuditRepository
from agentforge.platform.infrastructure.memory_connector_repository import (
    MemoryConnectorRepository,
)
from agentforge.platform.infrastructure.memory_cost_repository import MemoryCostRepository
from agentforge.platform.infrastructure.memory_evaluation_repository import (
    MemoryEvaluationRepository,
)
from agentforge.platform.infrastructure.memory_knowledge_repository import MemoryKnowledgeRepository
from agentforge.platform.infrastructure.memory_outbox_store import MemoryOutboxStore
from agentforge.platform.infrastructure.memory_rbac_repository import MemoryRbacRepository
from agentforge.platform.infrastructure.memory_regression_repository import (
    MemoryRegressionRepository,
)
from agentforge.platform.infrastructure.memory_reply_connector import MemoryReplyConnector
from agentforge.platform.infrastructure.memory_report_run_repository import (
    MemoryReportRunRepository,
)
from agentforge.platform.infrastructure.memory_scheduled_report_repository import (
    MemoryScheduledReportRepository,
)
from agentforge.platform.infrastructure.memory_tenant_quota_repository import (
    MemoryTenantQuotaRepository,
)
from agentforge.platform.infrastructure.memory_ticket_repository import MemoryTicketRepository
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore
from agentforge.platform.infrastructure.sqlalchemy_audit_repository import SQLAlchemyAuditRepository
from agentforge.platform.infrastructure.sqlalchemy_connector_repository import (
    SQLAlchemyConnectorRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_cost_repository import SQLAlchemyCostRepository
from agentforge.platform.infrastructure.sqlalchemy_evaluation_repository import (
    SQLAlchemyEvaluationRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_knowledge_repository import (
    SQLAlchemyKnowledgeRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_regression_repository import (
    SQLAlchemyRegressionRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_report_run_repository import (
    SQLAlchemyReportRunRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_scheduled_report_repository import (
    SQLAlchemyScheduledReportRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_tenant_quota_repository import (
    SQLAlchemyTenantQuotaRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_ticket_repository import (
    SQLAlchemyTicketRepository,
)
from agentforge.platform.settings import get_settings

DEFAULT_PROFILES = [
    ModelProfile(
        name="fast-local",
        provider="local",
        model_id="static-local",
        capability_score=5.0,
        cost_per_1k_tokens=0.001,
        avg_latency_ms=500,
        task_types=["classification", "general"],
    ),
    ModelProfile(
        name="balanced-cloud",
        provider="litellm",
        model_id="gpt-4.1-mini",
        capability_score=8.0,
        cost_per_1k_tokens=0.01,
        avg_latency_ms=1800,
        task_types=["drafting", "general"],
    ),
]


class ServiceContainer:
    def __init__(
        self,
        repository,
        classifier,
        knowledge_repository,
        model_gateway,
        cost_repository,
        outbox_store=None,
        workflow_client=None,
        reply_connector=None,
        audit_repository=None,
        authenticator: ApiKeyAuthenticator | None = None,
        evaluation_repository=None,
        regression_repository=None,
        connector_registry=None,
        connector_repository=None,
        adapter_factory=None,
        rbac_repository=None,
        policy_engine=None,
        openfga_client=None,
        tenant_quota_repository=None,
        scheduled_report_repository=None,
        run_repository=None,
        default_report_retention_days: int | None = None,
    ) -> None:
        self.repository = repository
        self.classifier = classifier
        self.knowledge_repository = knowledge_repository
        self.model_gateway = model_gateway
        self.cost_repository = cost_repository
        self.outbox_store = outbox_store
        self.workflow_client = workflow_client
        self.reply_connector = reply_connector
        self.audit_repository = audit_repository
        self.authenticator = authenticator or ApiKeyAuthenticator(enabled=False)
        self.evaluation_repository = evaluation_repository
        if regression_repository is None:
            regression_repository = MemoryRegressionRepository()
        self.regression_repository = regression_repository
        if connector_registry is None:
            connector_registry = ConnectorRegistry()
        self.connector_registry = connector_registry
        if connector_repository is None:
            connector_repository = MemoryConnectorRepository()
        self.connector_repository = connector_repository
        if adapter_factory is None:
            adapter_factory = build_openapi_adapter
        self.adapter_factory = adapter_factory
        if rbac_repository is None:
            rbac_repository = MemoryRbacRepository()
        self.rbac_repository = rbac_repository
        if openfga_client is None:
            from agentforge.platform.application.openfga_adapter import OpenFGAClient

            openfga_client = OpenFGAClient()
        self.openfga_client = openfga_client
        if policy_engine is None:
            from agentforge.platform.application.policy_engine import PolicyEngine

            policy_engine = PolicyEngine(policies=builtin_policies())
            policy_engine._relation_check = _async_relation_check(openfga_client)
        self.policy_engine = policy_engine
        if tenant_quota_repository is None:
            from agentforge.platform.infrastructure.memory_tenant_quota_repository import (
                MemoryTenantQuotaRepository,
            )

            tenant_quota_repository = MemoryTenantQuotaRepository()
        self.tenant_quota_repository = tenant_quota_repository
        self.dashboard_service = DashboardService(
            cost_repository,
            tenant_quota_repository,
            regression_repository,
        )
        if scheduled_report_repository is None:
            scheduled_report_repository = MemoryScheduledReportRepository()
        self.scheduled_report_repository = scheduled_report_repository
        if run_repository is None:
            run_repository = MemoryReportRunRepository()
        self.run_repository = run_repository
        self.report_service = ReportService(
            cost_repository,
            audit_repository,
            regression_repository,
            scheduled_report_repository,
            run_repository,
            default_retention_days=default_report_retention_days,
        )
        self.high_risk_authorizer = HighRiskActionAuthorizer(
            policy_engine,
            audit_repository,
            rbac_repository,
        )
        self.ticket_writeback_service = TicketWritebackService(
            connector_registry,
            audit_repository,
            high_risk_authorizer=self.high_risk_authorizer,
        )
        self.ticket_service = SupportTicketService(
            repository,
            classifier,
            reply_connector,
            audit_repository,
            evaluation_repository,
        )
        self.reranker = HybridReranker()
        self.knowledge_service = KnowledgeService(
            knowledge_repository,
            reranker=self.reranker,
        )
        self.retrieval_evaluation_service = RetrievalEvaluationService(
            knowledge_repository,
            self.reranker,
        )
        self.classification_evaluation_service = ClassificationEvaluationService(classifier)
        self.quality_gate_service = QualityGateService()
        self.prompt_registry = PromptRegistry()
        self.model_version_registry = ModelVersionRegistry()
        self.regression_runner = RegressionRunner(
            regression_repository,
            self.retrieval_evaluation_service,
            self.classification_evaluation_service,
            self.quality_gate_service,
        )
        self.reply_draft_service = ReplyDraftService(model_gateway)
        self.processing_service = SupportTicketProcessingService(
            self.ticket_service,
            repository,
            self.knowledge_service,
            self.reply_draft_service,
            cost_repository,
            audit_repository,
        )


_default_container: ServiceContainer | None = None


def _wrap_gateway(inner, cost_repository, tenant_quota_repository=None) -> QuotaAwareModelGateway:
    router = ModelRouter(DEFAULT_PROFILES)
    routed = RoutingModelGateway(router, inner)
    budget = get_settings().monthly_model_budget
    return QuotaAwareModelGateway(
        routed,
        cost_repository,
        budget,
        tenant_quota_repository=tenant_quota_repository,
    )


def _default_report_retention() -> int | None:
    """Global default report run retention (days) from environment.

    Applies to due schedules that don't define an explicit retention_days,
    giving run_due an automatic cleanup backstop. Absent/invalid -> disabled.
    """
    raw = os.environ.get("AGENTFORGE_REPORT_DEFAULT_RETENTION_DAYS")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def build_memory_container(
    model_gateway=None,
    authenticator: ApiKeyAuthenticator | None = None,
) -> ServiceContainer:
    cost_repository = MemoryCostRepository()
    audit_repository = MemoryAuditRepository()
    evaluation_repository = MemoryEvaluationRepository()
    reply_connector = MemoryReplyConnector()
    tenant_quota_repository = MemoryTenantQuotaRepository()
    scheduled_report_repository = MemoryScheduledReportRepository()
    run_repository = MemoryReportRunRepository()
    outbox_store = MemoryOutboxStore()
    return ServiceContainer(
        MemoryTicketRepository(),
        RuleBasedTicketClassifier(),
        MemoryKnowledgeRepository(),
        _wrap_gateway(
            model_gateway or StaticModelGateway(),
            cost_repository,
            tenant_quota_repository,
        ),
        cost_repository,
        reply_connector=reply_connector,
        audit_repository=audit_repository,
        authenticator=authenticator,
        evaluation_repository=evaluation_repository,
        tenant_quota_repository=tenant_quota_repository,
        scheduled_report_repository=scheduled_report_repository,
        run_repository=run_repository,
        outbox_store=outbox_store,
        default_report_retention_days=_default_report_retention(),
    )


def build_sqlalchemy_container(
    session_factory: async_sessionmaker[AsyncSession],
    model_gateway=None,
    workflow_client=None,
    reply_connector=None,
    authenticator: ApiKeyAuthenticator | None = None,
) -> ServiceContainer:
    cost_repository = SQLAlchemyCostRepository(session_factory)
    audit_repository = SQLAlchemyAuditRepository(session_factory)
    evaluation_repository = SQLAlchemyEvaluationRepository(session_factory)
    regression_repository = SQLAlchemyRegressionRepository(session_factory)
    tenant_quota_repository = SQLAlchemyTenantQuotaRepository(session_factory)
    scheduled_report_repository = SQLAlchemyScheduledReportRepository(session_factory)
    run_repository = SQLAlchemyReportRunRepository(session_factory)
    return ServiceContainer(
        SQLAlchemyTicketRepository(session_factory),
        RuleBasedTicketClassifier(),
        SQLAlchemyKnowledgeRepository(session_factory),
        _wrap_gateway(
            model_gateway or LiteLLMModelGateway(),
            cost_repository,
            tenant_quota_repository,
        ),
        cost_repository,
        SQLAlchemyOutboxStore(session_factory),
        workflow_client,
        reply_connector,
        audit_repository,
        authenticator,
        evaluation_repository,
        regression_repository,
        connector_repository=SQLAlchemyConnectorRepository(session_factory),
        tenant_quota_repository=tenant_quota_repository,
        scheduled_report_repository=scheduled_report_repository,
        run_repository=run_repository,
        default_report_retention_days=_default_report_retention(),
    )


def configure_container(container: ServiceContainer) -> None:
    global _default_container
    _default_container = container


def get_container() -> ServiceContainer:
    global _default_container
    if _default_container is None:
        _default_container = build_memory_container()
    return _default_container
