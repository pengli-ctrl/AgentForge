"""AgentForge 平台代码：runtime。

本模块负责依赖装配和服务容器构建，把仓储、模型网关、审计、配额、策略与工作流客户端组合成可运行的系统。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：ServiceContainer。
-
主要函数：build_memory_container、build_sqlalchemy_container、configure_container、get_container、boot_runtime。
"""

from __future__ import annotations

import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.api.security import ApiKeyAuthenticator
from agentforge.platform.application.builtin_policies import (
    _async_relation_check,
    builtin_policies,
    seed_rbac,
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
from agentforge.platform.observability.trace_recorder import TraceRecorder
from agentforge.platform.settings import get_settings

# 常量：DEFAULT_PROFILES。
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
    """ServiceContainer。

    ServiceContainer 封装相关领域行为，保持职责单一并降低调用方复杂度。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

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
        trace_recorder: TraceRecorder | None = None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            repository: Any，调用方传入的 repository 参数。
            classifier: Any，调用方传入的 classifier 参数。
            knowledge_repository: Any，调用方传入的 knowledge_repository 参数。
            model_gateway: Any，调用方传入的 model_gateway 参数。
            cost_repository: Any，调用方传入的 cost_repository 参数。
            outbox_store: Any，调用方传入的 outbox_store 参数。
            workflow_client: Any，调用方传入的 workflow_client 参数。
            reply_connector: Any，调用方传入的 reply_connector 参数。
            audit_repository: Any，调用方传入的 audit_repository 参数。
            authenticator: ApiKeyAuthenticator | None，调用方传入的 authenticator 参数。
            evaluation_repository: Any，调用方传入的 evaluation_repository 参数。
            regression_repository: Any，调用方传入的 regression_repository 参数。
            connector_registry: Any，调用方传入的 connector_registry 参数。
            connector_repository: Any，调用方传入的 connector_repository 参数。
            adapter_factory: Any，调用方传入的 adapter_factory 参数。
            rbac_repository: Any，调用方传入的 rbac_repository 参数。
            policy_engine: Any，调用方传入的 policy_engine 参数。
            openfga_client: Any，调用方传入的 openfga_client 参数。
            tenant_quota_repository: Any，调用方传入的 tenant_quota_repository 参数。
            scheduled_report_repository: Any，调用方传入的 scheduled_report_repository 参数。
            run_repository: Any，调用方传入的 run_repository 参数。
            default_report_retention_days: int | None，调用方传入的 default_report_retention_days 参数。
            trace_recorder: TraceRecorder | None，调用方传入的 trace_recorder 参数。

        Returns:
            None，函数执行后的结果。
        """
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
        if trace_recorder is None:
            trace_recorder = TraceRecorder()
        self.trace_recorder = trace_recorder
        self.dashboard_service = DashboardService(
            cost_repository,
            tenant_quota_repository,
            regression_repository,
        )
        self.dashboard_service.attach_trace_recorder(trace_recorder)
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


def _wrap_gateway(
    inner,
    cost_repository,
    tenant_quota_repository=None,
    trace_recorder: TraceRecorder | None = None,
) -> QuotaAwareModelGateway:
    """执行 _wrap_gateway 对应的逻辑，并返回处理结果。

    Args:
        inner: Any，调用方传入的 inner 参数。
        cost_repository: Any，调用方传入的 cost_repository 参数。
        tenant_quota_repository: Any，调用方传入的 tenant_quota_repository 参数。
        trace_recorder: TraceRecorder | None，调用方传入的 trace_recorder 参数。

    Returns:
        QuotaAwareModelGateway，函数执行后的结果。
    """
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
    """执行 _default_report_retention 对应的逻辑，并返回处理结果。

    Returns:
        int | None，函数执行后的结果。
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
    """构建目标对象，并返回调用方需要的结果。

    Args:
        model_gateway: Any，调用方传入的 model_gateway 参数。
        authenticator: ApiKeyAuthenticator | None，调用方传入的 authenticator 参数。

    Returns:
        ServiceContainer，函数执行后的结果。
    """
    cost_repository = MemoryCostRepository()
    audit_repository = MemoryAuditRepository()
    evaluation_repository = MemoryEvaluationRepository()
    reply_connector = MemoryReplyConnector()
    tenant_quota_repository = MemoryTenantQuotaRepository()
    scheduled_report_repository = MemoryScheduledReportRepository()
    run_repository = MemoryReportRunRepository()
    outbox_store = MemoryOutboxStore()
    trace_recorder = TraceRecorder()
    inner = model_gateway or StaticModelGateway(recorder=trace_recorder)
    return ServiceContainer(
        MemoryTicketRepository(),
        RuleBasedTicketClassifier(),
        MemoryKnowledgeRepository(),
        _wrap_gateway(
            inner,
            cost_repository,
            tenant_quota_repository,
            trace_recorder=trace_recorder,
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
        trace_recorder=trace_recorder,
    )


def build_sqlalchemy_container(
    session_factory: async_sessionmaker[AsyncSession],
    model_gateway=None,
    workflow_client=None,
    reply_connector=None,
    authenticator: ApiKeyAuthenticator | None = None,
) -> ServiceContainer:
    """构建目标对象，并返回调用方需要的结果。

    Args:
        session_factory: async_sessionmaker[AsyncSession]，调用方传入的 session_factory 参数。
        model_gateway: Any，调用方传入的 model_gateway 参数。
        workflow_client: Any，调用方传入的 workflow_client 参数。
        reply_connector: Any，调用方传入的 reply_connector 参数。
        authenticator: ApiKeyAuthenticator | None，调用方传入的 authenticator 参数。

    Returns:
        ServiceContainer，函数执行后的结果。
    """
    cost_repository = SQLAlchemyCostRepository(session_factory)
    audit_repository = SQLAlchemyAuditRepository(session_factory)
    evaluation_repository = SQLAlchemyEvaluationRepository(session_factory)
    regression_repository = SQLAlchemyRegressionRepository(session_factory)
    tenant_quota_repository = SQLAlchemyTenantQuotaRepository(session_factory)
    scheduled_report_repository = SQLAlchemyScheduledReportRepository(session_factory)
    run_repository = SQLAlchemyReportRunRepository(session_factory)
    trace_recorder = TraceRecorder()
    inner = model_gateway or LiteLLMModelGateway(recorder=trace_recorder)
    return ServiceContainer(
        SQLAlchemyTicketRepository(session_factory),
        RuleBasedTicketClassifier(),
        SQLAlchemyKnowledgeRepository(session_factory),
        _wrap_gateway(
            inner,
            cost_repository,
            tenant_quota_repository,
            trace_recorder=trace_recorder,
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
        trace_recorder=trace_recorder,
    )


def configure_container(container: ServiceContainer) -> None:
    """执行 configure_container 对应的逻辑，并返回处理结果。

    Args:
        container: ServiceContainer，调用方传入的 container 参数。

    Returns:
        None，函数执行后的结果。
    """
    global _default_container
    _default_container = container


def get_container() -> ServiceContainer:
    """读取并返回指定数据，并返回调用方需要的结果。

    Returns:
        ServiceContainer，函数执行后的结果。
    """
    global _default_container
    if _default_container is None:
        _default_container = build_memory_container()
    return _default_container


logger = logging.getLogger(__name__)


async def boot_runtime(container: ServiceContainer) -> None:
    """执行 boot_runtime 对应的逻辑，并返回处理结果。

    Args:
        container: ServiceContainer，调用方传入的 container 参数。

    Returns:
        None，函数执行后的结果。
    """
    try:
        await seed_rbac(container.rbac_repository)
    except Exception as exc:  # noqa: BLE001 - startup resilience
        logger.warning("boot_runtime: seed_rbac failed: %s", exc)
    try:
        await container.connector_registry.load_from_repository(
            container.connector_repository,
            adapter_factory=container.adapter_factory,
        )
    except Exception as exc:  # noqa: BLE001 - startup resilience
        logger.warning("boot_runtime: connector load_from_repository failed: %s", exc)
