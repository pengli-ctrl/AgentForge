"""运行时模块。"""

from __future__ import annotations

import logging
import os
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.api.security import ApiKeyAuthenticator
from agentforge.platform.application.authorization_service import AuthorizationService
from agentforge.platform.application.builtin_policies import (
    _async_relation_check,
    builtin_policies,
    seed_rbac,
)
from agentforge.platform.application.chunked_upload_service import ChunkedUploadService
from agentforge.platform.application.classification_evaluation_service import (
    ClassificationEvaluationService,
)
from agentforge.platform.application.connector_registry import ConnectorRegistry
from agentforge.platform.application.dashboard_service import DashboardService
from agentforge.platform.application.knowledge_service import KnowledgeService
from agentforge.platform.application.model_router import ModelRouter
from agentforge.platform.application.openapi_adapter import build_openapi_adapter
from agentforge.platform.application.prompt_registry import PromptRegistry
from agentforge.platform.application.quality_gate_service import QualityGateService
from agentforge.platform.application.quota_service import QuotaAwareModelGateway
from agentforge.platform.application.regression_runner import RegressionRunner
from agentforge.platform.application.report_service import ReportService
from agentforge.platform.application.reranker import HybridReranker
from agentforge.platform.application.retrieval_evaluation_service import RetrievalEvaluationService
from agentforge.platform.application.routing_model_gateway import RoutingModelGateway
from agentforge.platform.application.saas_plans import PlanCatalog
from agentforge.platform.application.tenant_lifecycle_service import TenantLifecycleService
from agentforge.platform.application.tenant_module_service import (
    TenantModuleConfigAccessor,
    TenantModuleService,
)
from agentforge.platform.application.usage_metering_service import (
    UsageMeteringAdapter,
    UsageMeteringService,
)
from agentforge.platform.application.version_registry import ModelVersionRegistry
from agentforge.platform.domain.model import ModelProfile
from agentforge.platform.infrastructure.llm.litellm_gateway import LiteLLMModelGateway
from agentforge.platform.infrastructure.llm.static_gateway import StaticModelGateway
from agentforge.platform.infrastructure.memory_audit_repository import MemoryAuditRepository
from agentforge.platform.infrastructure.memory_connector_repository import MemoryConnectorRepository
from agentforge.platform.infrastructure.memory_cost_repository import MemoryCostRepository
from agentforge.platform.infrastructure.memory_evaluation_repository import (
    MemoryEvaluationRepository,
)
from agentforge.platform.infrastructure.memory_knowledge_repository import MemoryKnowledgeRepository
from agentforge.platform.infrastructure.memory_object_store import MemoryObjectStore
from agentforge.platform.infrastructure.memory_outbox_store import MemoryOutboxStore
from agentforge.platform.infrastructure.memory_rbac_repository import MemoryRbacRepository
from agentforge.platform.infrastructure.memory_regression_repository import (
    MemoryRegressionRepository,
)
from agentforge.platform.infrastructure.memory_report_run_repository import (
    MemoryReportRunRepository,
)
from agentforge.platform.infrastructure.memory_scheduled_report_repository import (
    MemoryScheduledReportRepository,
)
from agentforge.platform.infrastructure.memory_tenant_account_repository import (
    MemoryTenantAccountRepository,
)
from agentforge.platform.infrastructure.memory_tenant_module_repository import (
    MemoryTenantModuleRepository,
)
from agentforge.platform.infrastructure.memory_tenant_quota_repository import (
    MemoryTenantQuotaRepository,
)
from agentforge.platform.infrastructure.memory_upload_session_repository import (
    MemoryUploadSessionRepository,
)
from agentforge.platform.infrastructure.memory_usage_repository import MemoryUsageRepository
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore
from agentforge.platform.infrastructure.persistence import SQLAlchemyPersistence
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
from agentforge.platform.infrastructure.sqlalchemy_tenant_account_repository import (
    SQLAlchemyTenantAccountRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_tenant_module_repository import (
    SQLAlchemyTenantModuleRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_tenant_quota_repository import (
    SQLAlchemyTenantQuotaRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_upload_session_repository import (
    SQLAlchemyUploadSessionRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_usage_repository import SQLAlchemyUsageRepository
from agentforge.platform.observability.trace_recorder import TraceRecorder
from agentforge.platform.sdk.module import ModuleConfig, ModuleContext
from agentforge.platform.sdk.ports import (
    AuthenticatorPort,
    AuthorizationPort,
    ChunkedUploadPort,
    ConnectorCatalogPort,
    CostPort,
    EvaluationPort,
    KnowledgePort,
    ModuleAccessPort,
    OcrPort,
    RbacPort,
    UsagePort,
    WorkflowClientPort,
)
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
    """承载共享内核依赖的进程级容器。"""

    def __init__(
        self,
        knowledge_repository,
        model_gateway,
        cost_repository,
        outbox_store=None,
        workflow_client=None,
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
        classification_evaluation_service: ClassificationEvaluationService | None = None,
        persistence=None,
        tenant_module_repository=None,
        tenant_account_repository=None,
        usage_repository=None,
        plan_catalog: PlanCatalog | None = None,
        ocr=None,
        object_store=None,
        upload_session_repository=None,
    ) -> None:
        """初始化 ServiceContainer。

        Args:
            knowledge_repository: 知识仓储。
            model_gateway: 模型网关。
            cost_repository: 成本仓储。
            outbox_store: Outbox存储。
            workflow_client: 工作流客户端。
            audit_repository: 审计仓储。
            authenticator: 认证器实例。
            evaluation_repository: 评估仓储。
            regression_repository: 回归仓储。
            connector_registry: 连接器注册表。
            connector_repository: 连接器仓储。
            adapter_factory: 适配器工厂。
            rbac_repository: RBAC仓储。
            policy_engine: 策略引擎。
            openfga_client: 客户端。
            tenant_quota_repository: 租户配额仓储。
            scheduled_report_repository: 报告仓储。
            run_repository: 运行仓储。
            default_report_retention_days: 默认报告保留。
            trace_recorder: 链路记录器。
            classification_evaluation_service: 分类评估服务。
                classification evaluation service。
            persistence: 持久化。
            tenant_module_repository: 租户模块仓储。
            tenant_account_repository: 租户仓储。
            usage_repository: 用量仓储。
            plan_catalog: 套餐目录。
            ocr: OCR。
            object_store: 对象存储。
            upload_session_repository: 上传会话仓储。
        """
        self.knowledge_repository = knowledge_repository
        self.model_gateway = model_gateway
        self.persistence = persistence
        self.ocr = ocr
        self.object_store = object_store or MemoryObjectStore()
        if upload_session_repository is None:
            upload_session_repository = MemoryUploadSessionRepository()
        self.upload_session_repository = upload_session_repository
        self.upload_service = ChunkedUploadService(
            upload_session_repository,
            self.object_store,
        )
        if tenant_module_repository is None:
            tenant_module_repository = MemoryTenantModuleRepository()
        self.tenant_module_repository = tenant_module_repository
        self.tenant_account_repository = (
            tenant_account_repository or MemoryTenantAccountRepository()
        )
        self.usage_repository = usage_repository or MemoryUsageRepository()
        self.plan_catalog = plan_catalog or PlanCatalog.from_settings(get_settings())
        self.cost_repository = cost_repository
        self.outbox_store = outbox_store
        self.workflow_client = workflow_client
        self.tenant_module_service = TenantModuleService(
            tenant_module_repository,
            audit_repository,
            outbox_store,
            self.tenant_account_repository,
        )
        self.tenant_lifecycle_service = TenantLifecycleService(
            self.tenant_account_repository,
            self.tenant_module_service,
            self.plan_catalog,
            quota_repository=tenant_quota_repository,
            audit=audit_repository,
            outbox=outbox_store,
        )
        self.usage_metering_service = UsageMeteringService(
            self.usage_repository,
            self.tenant_account_repository,
            self.plan_catalog,
            audit=audit_repository,
            outbox=outbox_store,
        )
        self.usage_port = UsageMeteringAdapter(self.usage_metering_service)
        self.upload_service.set_usage_meter(self.usage_port)
        set_model_usage = getattr(self.model_gateway, "set_usage_meter", None)
        if callable(set_model_usage):
            set_model_usage(self.usage_port)
        if self.workflow_client is not None:
            set_workflow_usage = getattr(self.workflow_client, "set_usage_meter", None)
            if callable(set_workflow_usage):
                set_workflow_usage(self.usage_port)
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
        self.authorization_service = AuthorizationService(
            policy_engine,
            rbac_repository,
            audit_repository,
        )

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

        self.reranker = HybridReranker()
        self.knowledge_service = KnowledgeService(
            knowledge_repository,
            reranker=self.reranker,
        )
        self.retrieval_evaluation_service = RetrievalEvaluationService(
            knowledge_repository,
            self.reranker,
        )
        self.classification_evaluation_service = classification_evaluation_service
        self.quality_gate_service = QualityGateService()
        self.prompt_registry = PromptRegistry()
        self.model_version_registry = ModelVersionRegistry()
        self.regression_runner = RegressionRunner(
            regression_repository,
            self.retrieval_evaluation_service,
            self.classification_evaluation_service,
            self.quality_gate_service,
        )


_default_container: ServiceContainer | None = None


def _wrap_gateway(
    inner,
    cost_repository,
    tenant_quota_repository=None,
    trace_recorder: TraceRecorder | None = None,
) -> QuotaAwareModelGateway:
    """包装网关。

    Args:
        inner: 输入参数。
        cost_repository: 成本仓储。
        tenant_quota_repository: 租户配额仓储。
        trace_recorder: 链路记录器。

    Returns:
        配额模型网关结果。
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
    """处理默认报告保留。

    Returns:
        整数无结果。
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
    workflow_client=None,
    classification_evaluation_service: ClassificationEvaluationService | None = None,
    ocr=None,
    object_store=None,
) -> ServiceContainer:
    """构建只包含共享内核能力的内存容器。

    Args:
        model_gateway: 模型网关。
        authenticator: 认证器实例。
        workflow_client: 工作流客户端。
        classification_evaluation_service: 分类评估服务。
            classification evaluation service。
        ocr: OCR。
        object_store: 对象存储。

    Returns:
        服务容器结果。
    """
    cost_repository = MemoryCostRepository()
    audit_repository = MemoryAuditRepository()
    evaluation_repository = MemoryEvaluationRepository()
    tenant_quota_repository = MemoryTenantQuotaRepository()
    scheduled_report_repository = MemoryScheduledReportRepository()
    run_repository = MemoryReportRunRepository()
    outbox_store = MemoryOutboxStore()
    trace_recorder = TraceRecorder()
    inner = model_gateway or StaticModelGateway(recorder=trace_recorder)
    return ServiceContainer(
        knowledge_repository=MemoryKnowledgeRepository(),
        model_gateway=_wrap_gateway(
            inner,
            cost_repository,
            tenant_quota_repository,
            trace_recorder=trace_recorder,
        ),
        cost_repository=cost_repository,
        outbox_store=outbox_store,
        workflow_client=workflow_client,
        audit_repository=audit_repository,
        authenticator=authenticator,
        evaluation_repository=evaluation_repository,
        tenant_quota_repository=tenant_quota_repository,
        scheduled_report_repository=scheduled_report_repository,
        run_repository=run_repository,
        tenant_account_repository=MemoryTenantAccountRepository(),
        usage_repository=MemoryUsageRepository(),
        plan_catalog=PlanCatalog.from_settings(get_settings()),
        default_report_retention_days=_default_report_retention(),
        trace_recorder=trace_recorder,
        classification_evaluation_service=classification_evaluation_service,
        ocr=ocr,
        object_store=object_store,
        upload_session_repository=MemoryUploadSessionRepository(),
    )


def build_sqlalchemy_container(
    session_factory: async_sessionmaker[AsyncSession],
    model_gateway=None,
    workflow_client=None,
    authenticator: ApiKeyAuthenticator | None = None,
    classification_evaluation_service: ClassificationEvaluationService | None = None,
    ocr=None,
    object_store=None,
) -> ServiceContainer:
    """构建SQLAlchemy容器。

    Args:
        session_factory: 数据库会话工厂。
        model_gateway: 模型网关。
        workflow_client: 工作流客户端。
        authenticator: 认证器实例。
        classification_evaluation_service: 分类评估服务。
            classification evaluation service。
        ocr: OCR。
        object_store: 对象存储。

    Returns:
        服务容器结果。
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
        knowledge_repository=SQLAlchemyKnowledgeRepository(session_factory),
        model_gateway=_wrap_gateway(
            inner,
            cost_repository,
            tenant_quota_repository,
            trace_recorder=trace_recorder,
        ),
        cost_repository=cost_repository,
        outbox_store=SQLAlchemyOutboxStore(session_factory),
        workflow_client=workflow_client,
        audit_repository=audit_repository,
        authenticator=authenticator,
        evaluation_repository=evaluation_repository,
        regression_repository=regression_repository,
        connector_repository=SQLAlchemyConnectorRepository(session_factory),
        tenant_quota_repository=tenant_quota_repository,
        scheduled_report_repository=scheduled_report_repository,
        run_repository=run_repository,
        default_report_retention_days=_default_report_retention(),
        trace_recorder=trace_recorder,
        classification_evaluation_service=classification_evaluation_service,
        persistence=SQLAlchemyPersistence(session_factory),
        tenant_module_repository=SQLAlchemyTenantModuleRepository(session_factory),
        tenant_account_repository=SQLAlchemyTenantAccountRepository(session_factory),
        usage_repository=SQLAlchemyUsageRepository(session_factory),
        plan_catalog=PlanCatalog.from_settings(get_settings()),
        ocr=ocr,
        object_store=object_store,
        upload_session_repository=SQLAlchemyUploadSessionRepository(session_factory),
    )


def build_module_context(
    container: ServiceContainer,
    *,
    module_name: str = "",
    config: ModuleConfig | None = None,
) -> ModuleContext:
    """从平台容器构建模块可用的共享端口上下文。

    Args:
        container: 服务容器。
        module_name: 模块名称。
        config: 组件配置。

    Returns:
        模块上下文结果。
    """
    return ModuleContext(
        audit=container.audit_repository,
        authorization=cast(AuthorizationPort, container.authorization_service),
        outbox=container.outbox_store,
        connectors=cast(ConnectorCatalogPort, container.connector_registry),
        knowledge=cast(KnowledgePort, container.knowledge_service),
        models=container.model_gateway,
        policy=container.policy_engine,
        cost=cast(CostPort, container.cost_repository),
        evaluation=cast(EvaluationPort | None, container.evaluation_repository),
        identity=cast(RbacPort, container.rbac_repository),
        module_access=cast(ModuleAccessPort, container.tenant_module_service),
        workflow=cast(WorkflowClientPort | None, container.workflow_client),
        persistence=container.persistence,
        ocr=cast(OcrPort | None, container.ocr),
        object_store=container.object_store,
        uploads=cast(ChunkedUploadPort, container.upload_service),
        config=config or ModuleConfig(),
        tenant_config=(
            TenantModuleConfigAccessor(container.tenant_module_service, module_name)
            if module_name
            else None
        ),
        authenticator=cast(AuthenticatorPort, container.authenticator),
        usage=cast(UsagePort, container.usage_port),
    )


def configure_container(container: ServiceContainer) -> None:
    """配置容器。

    Args:
        container: 服务容器。
    """
    global _default_container
    _default_container = container


def get_container() -> ServiceContainer:
    """获取容器。

    Returns:
        服务容器结果。
    """
    global _default_container
    if _default_container is None:
        _default_container = build_memory_container()
    return _default_container


logger = logging.getLogger(__name__)


async def boot_runtime(container: ServiceContainer) -> None:
    """处理运行时。

    Args:
        container: 服务容器。
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
