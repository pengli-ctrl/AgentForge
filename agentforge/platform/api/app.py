"""AgentForge 平台 API 层：app。

本模块创建 FastAPI 应用，注册中间件、鉴权、业务路由、管理接口和启动生命周期逻辑。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_platform_app。
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agentforge.platform.api.audit_router import create_audit_router
from agentforge.platform.api.authorization_router import create_authorization_router
from agentforge.platform.api.connector_router import create_connector_router
from agentforge.platform.api.console_router import create_console_router
from agentforge.platform.api.cost_router import create_cost_router
from agentforge.platform.api.evaluation_router import create_evaluation_router
from agentforge.platform.api.feishu_router import create_feishu_router
from agentforge.platform.api.knowledge_router import create_knowledge_router
from agentforge.platform.api.outbox_router import create_outbox_router
from agentforge.platform.api.policies_router import create_policies_router
from agentforge.platform.api.quota_router import create_quota_router
from agentforge.platform.api.rbac_router import create_rbac_router
from agentforge.platform.api.regression_router import create_regression_router
from agentforge.platform.api.release_router import create_release_router
from agentforge.platform.api.security import ApiKeyAuthenticator
from agentforge.platform.api.support_router import create_support_router
from agentforge.platform.infrastructure.db.base import create_session_factory
from agentforge.platform.infrastructure.feishu_reply_connector import FeishuReplyConnector
from agentforge.platform.infrastructure.temporal.client import TemporalWorkflowClient
from agentforge.platform.runtime import (
    ServiceContainer,
    boot_runtime,
    build_memory_container,
    build_sqlalchemy_container,
)
from agentforge.platform.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def _resolve_auth_enabled(settings: Settings) -> bool:
    """推导平台层鉴权实际是否生效（fail-closed）。

    P0-1 安全默认值反转：默认"要求鉴权"，不再默认裸奔。
      - 已配置 key（租户或 admin）→ 按 settings.auth_enabled（默认 True=生效）。
      - 未配置 key 且生产环境(prod/staging) → 拒绝启动并给出明确指引，
        必须显式设置 AGENTFORGE_ALLOW_NO_AUTH=true 才放行。
      - 未配置 key 且非生产环境(dev) → 仅本地开发降级为关闭并打印告警。
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
) -> FastAPI:
    """创建应用实例，完成依赖装配、中间件注册和路由挂载。

    Args:
        container: ServiceContainer | None，调用方传入的 container 参数。
        feishu_encrypt_key: str | None，调用方传入的 feishu_encrypt_key 参数。
        feishu_verification_token: str | None，调用方传入的 feishu_verification_token 参数。

    Returns:
        FastAPI，函数执行后的结果。
    """
    settings = get_settings()
    authenticator = ApiKeyAuthenticator(
        enabled=_resolve_auth_enabled(settings),
        tenant_keys=settings.api_keys,
        admin_key=settings.admin_api_key,
    )
    if container is None:
        if settings.env in {"prod", "staging"}:
            session_factory = create_session_factory(settings.database_url)
            workflow_client = TemporalWorkflowClient(
                settings.temporal_address,
                settings.temporal_namespace,
            )
            reply_connector = FeishuReplyConnector(
                settings.feishu_app_id,
                settings.feishu_app_secret,
            )
            container = build_sqlalchemy_container(
                session_factory,
                workflow_client=workflow_client,
                reply_connector=reply_connector,
                authenticator=authenticator,
            )
        else:
            container = build_memory_container(authenticator=authenticator)

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        # 仓储层行为验证。
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        """执行 _lifespan 对应的逻辑，并返回处理结果。

        Args:
            app: FastAPI，调用方传入的 app 参数。

        Returns:
            None，函数执行后的结果。
        """
        if container is not None:
            await boot_runtime(container)
        yield

    app = FastAPI(title="AgentForge Platform", version="0.5.0", lifespan=_lifespan)
    app.include_router(
        create_support_router(
            container,
            webhook_secret=settings.events_im_webhook_secret,
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
            ticket_repository=getattr(container, "repository", None),
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
    app.include_router(
        create_feishu_router(
            container,
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
        """执行 live 对应的逻辑，并返回处理结果。

        Returns:
            dict[str, str]，函数执行后的结果。
        """
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        """执行 ready 对应的逻辑，并返回处理结果。

        Returns:
            dict[str, str]，函数执行后的结果。
        """
        return {"status": "ready", "env": settings.env}

    return app
