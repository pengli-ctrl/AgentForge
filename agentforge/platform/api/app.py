"""应用模块。"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from agentforge import __version__
from agentforge.observability.metrics import get_metrics_collector
from agentforge.platform.api.audit_router import create_audit_router
from agentforge.platform.api.authorization_router import create_authorization_router
from agentforge.platform.api.connector_router import create_connector_router
from agentforge.platform.api.console_router import create_console_router
from agentforge.platform.api.cost_router import create_cost_router
from agentforge.platform.api.evaluation_router import create_evaluation_router
from agentforge.platform.api.knowledge_router import create_knowledge_router
from agentforge.platform.api.module_admin_router import create_module_admin_router
from agentforge.platform.api.outbox_router import create_outbox_router
from agentforge.platform.api.policies_router import create_policies_router
from agentforge.platform.api.quota_router import create_quota_router
from agentforge.platform.api.rbac_router import create_rbac_router
from agentforge.platform.api.regression_router import create_regression_router
from agentforge.platform.api.release_router import create_release_router
from agentforge.platform.api.security import ApiKeyAuthenticator
from agentforge.platform.api.tenant_control_router import create_tenant_control_router
from agentforge.platform.application.classification_evaluation_service import (
    ClassificationEvaluationService,
)
from agentforge.platform.core import ModuleRegistry
from agentforge.platform.infrastructure.db.base import create_session_factory
from agentforge.platform.infrastructure.s3_object_store import S3ObjectStore
from agentforge.platform.infrastructure.temporal.client import TemporalWorkflowClient
from agentforge.platform.module_catalog import (
    ModuleAssemblyContext,
    build_builtin_modules,
    build_module_config,
    build_support_notification_gateway,
)
from agentforge.platform.modules.expense.ports import ExpenseClaimRepository
from agentforge.platform.modules.support.api.feishu_router import create_feishu_router
from agentforge.platform.modules.support.application.classifier import RuleBasedTicketClassifier
from agentforge.platform.modules.support.infrastructure.feishu_reply_connector import (
    FeishuReplyConnector,
)
from agentforge.platform.modules.support.ports import (
    NotificationPort,
    ReplyConnectorPort,
    TicketRepository,
)
from agentforge.platform.modules.support.runtime import get_support_runtime
from agentforge.platform.plugin_loader import load_module_plugins
from agentforge.platform.runtime import (
    ServiceContainer,
    boot_runtime,
    build_memory_container,
    build_module_context,
    build_sqlalchemy_container,
)
from agentforge.platform.sdk.module import BusinessModule
from agentforge.platform.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def _resolve_auth_enabled(settings: Settings) -> bool:
    """解析鉴权启用。

    Args:
        settings: 应用配置。

    Returns:
        操作是否成功。

    Raises:
        RuntimeError: 运行时依赖或状态不满足要求时抛出。
    """
    has_keys = bool(settings.api_keys or settings.admin_api_key)
    if has_keys:
        return settings.auth_enabled
    if settings.env in {"prod", "staging"}:
        if os.environ.get("AGENTFORGE_ALLOW_NO_AUTH", "").lower() == "true":
            logger.warning(
                "Platform auth disabled via AGENTFORGE_ALLOW_NO_AUTH=true while no "
                "API keys are configured in env=%s. Do NOT expose publicly.",
                settings.env,
            )
            return False
        raise RuntimeError(
            "Platform authentication is enabled by default (fail-closed) but no "
            "API keys are configured in env=%s. Set AGENTFORGE_API_KEYS / "
            "AGENTFORGE_ADMIN_API_KEY, or explicitly set "
            "AGENTFORGE_ALLOW_NO_AUTH=true only for non-production use." % settings.env
        )
    logger.warning(
        "Platform auth disabled in dev env=%s because no API keys are configured. "
        "Set AGENTFORGE_API_KEYS / AGENTFORGE_ADMIN_API_KEY to enable authentication.",
        settings.env,
    )
    return False


def create_platform_app(
    container: ServiceContainer | None = None,
    feishu_encrypt_key: str | None = None,
    feishu_verification_token: str | None = None,
    *,
    support_ticket_repository: TicketRepository | None = None,
    support_reply_connector: ReplyConnectorPort | None = None,
    support_notification_gateway: NotificationPort | None = None,
    expense_claim_repository: ExpenseClaimRepository | None = None,
    extra_modules: Sequence[BusinessModule] = (),
    load_plugins: bool = True,
) -> FastAPI:
    """创建平台应用。

    Args:
        container: 服务容器。
        feishu_encrypt_key: 飞书键。
        feishu_verification_token: 飞书核验令牌。
        support_ticket_repository: 客服工单仓储。
        support_reply_connector: 客服回复连接器。
        support_notification_gateway: 客服通知网关。
        expense_claim_repository: 报销报销单仓储。
        extra_modules: 模块。
        load_plugins: 加载。

    Yields:
        逐次生成的结果。

    Raises:
        RuntimeError: 运行时依赖或状态不满足要求时抛出。
    """
    settings = get_settings()
    authenticator = ApiKeyAuthenticator(
        enabled=_resolve_auth_enabled(settings),
        tenant_keys=settings.api_keys,
        admin_key=settings.admin_api_key,
    )
    session_factory = None
    if container is None:
        if settings.env in {"prod", "staging"}:
            session_factory = create_session_factory(settings.database_url)
            workflow_client = TemporalWorkflowClient(
                settings.temporal_address,
                settings.temporal_namespace,
            )
            container = build_sqlalchemy_container(
                session_factory,
                workflow_client=workflow_client,
                authenticator=authenticator,
                object_store=S3ObjectStore.from_settings(settings),
                classification_evaluation_service=ClassificationEvaluationService(
                    RuleBasedTicketClassifier()
                ),
            )
            if support_reply_connector is None:
                support_reply_connector = FeishuReplyConnector(
                    settings.feishu_app_id,
                    settings.feishu_app_secret,
                )
        else:
            container = build_memory_container(
                authenticator=authenticator,
                classification_evaluation_service=ClassificationEvaluationService(
                    RuleBasedTicketClassifier()
                ),
            )

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        # 仓储层行为验证。
        """管理平台应用启动和关闭生命周期。

        Args:
            app: 应用。

        Yields:
            逐次生成的结果。
        """
        if container is not None:
            await boot_runtime(container)
            await module_registry.run_startup_hooks()
        yield

    if container is None:
        raise RuntimeError("platform container was not initialized")

    app = FastAPI(title="AgentForge Platform", version=__version__, lifespan=_lifespan)

    enabled_modules = settings.enabled_module_names
    notification_gateway = support_notification_gateway or build_support_notification_gateway(
        settings
    )
    builtin_modules = build_builtin_modules(
        ModuleAssemblyContext(
            container=container,
            enabled_modules=enabled_modules,
            session_factory=session_factory,
            support_ticket_repository=support_ticket_repository,
            support_reply_connector=support_reply_connector,
            support_notification_gateway=notification_gateway,
            expense_claim_repository=expense_claim_repository,
            support_webhook_secret=settings.events_im_webhook_secret,
        )
    )
    plugin_modules = load_module_plugins() if load_plugins else []
    application_modules = [*builtin_modules, *plugin_modules, *extra_modules]
    for module in application_modules:
        container.tenant_module_service.register_module(
            module.manifest,
            build_module_config(module.manifest, settings).values,
        )
    module_registry = ModuleRegistry(
        lambda manifest: build_module_context(
            container,
            module_name=manifest.name,
            config=build_module_config(manifest, settings),
        )
    )
    for module in application_modules:
        module_registry.register(module)
    module_registry.validate()
    support_runtime = get_support_runtime() if "support" in enabled_modules else None
    module_registry.mount_routes(app)
    app.state.module_registry = module_registry
    app.state.container = container

    @app.get("/metrics")
    async def platform_metrics() -> PlainTextResponse:
        """获取平台指标。

        Returns:
            文本响应结果。
        """
        parts = [get_metrics_collector().generate_metrics().strip()]
        for provider in module_registry.iter_metric_providers():
            provided = (await provider()).strip()
            if provided:
                parts.append(provided)
        return PlainTextResponse(
            content="\n".join(part for part in parts if part) + "\n",
            media_type="text/plain; version=0.0.4",
        )

    app.include_router(
        create_module_admin_router(
            container.tenant_module_service,
            known_modules=tuple(module.manifest.name for module in module_registry.list_modules()),
            authenticator=authenticator,
        )
    )
    app.include_router(
        create_tenant_control_router(
            container.tenant_lifecycle_service,
            container.usage_metering_service,
            container.plan_catalog,
            authenticator=authenticator,
            outbox_store=getattr(container, "outbox_store", None),
        )
    )
    app.include_router(create_authorization_router(container))
    app.include_router(create_knowledge_router(container))
    app.include_router(create_outbox_router(container))
    app.include_router(create_audit_router(container))
    app.include_router(create_cost_router(container))
    app.include_router(create_evaluation_router(container))
    app.include_router(create_release_router(container))
    app.include_router(create_regression_router(container))
    app.include_router(
        create_rbac_router(
            rbac_repository=container.rbac_repository,
            policy_engine=container.policy_engine,
        )
    )
    app.include_router(create_policies_router(policy_engine=container.policy_engine))
    app.include_router(
        create_quota_router(
            quota_repository=container.tenant_quota_repository,
            cost_repository=container.cost_repository,
        )
    )
    app.include_router(
        create_console_router(
            quota_repository=container.tenant_quota_repository,
            cost_repository=container.cost_repository,
            outbox_store=getattr(container, "outbox_store", None),
            audit_repository=getattr(container, "audit_repository", None),
            ticket_repository=support_runtime.repository if support_runtime else None,
            dashboard_service=getattr(container, "dashboard_service", None),
            connector_registry=getattr(container, "connector_registry", None),
            connector_repository=getattr(container, "connector_repository", None),
            authenticator=authenticator,
            report_service=getattr(container, "report_service", None),
        )
    )
    app.include_router(
        create_connector_router(
            container.connector_registry,
            repository=container.connector_repository,
            adapter_factory=container.adapter_factory,
            authenticator=authenticator,
        )
    )
    if support_runtime is not None:
        app.include_router(
            create_feishu_router(
                support_runtime,
                encrypt_key=(
                    feishu_encrypt_key
                    if feishu_encrypt_key is not None
                    else settings.feishu_encrypt_key
                ),
                verification_token=(
                    feishu_verification_token
                    if feishu_verification_token is not None
                    else settings.feishu_verification_token
                ),
                signature_max_age_seconds=settings.feishu_signature_max_age_seconds,
            )
        )

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        """提供存活探针结果。

        Returns:
            结构化结果字典。
        """
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        """提供就绪探针结果。

        Returns:
            结构化结果字典。
        """
        return {"status": "ready", "env": settings.env}

    return app
