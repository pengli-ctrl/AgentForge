from __future__ import annotations

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
from agentforge.platform.settings import get_settings


def create_platform_app(
    container: ServiceContainer | None = None,
    feishu_encrypt_key: str | None = None,
    feishu_verification_token: str | None = None,
) -> FastAPI:
    settings = get_settings()
    authenticator = ApiKeyAuthenticator(
        enabled=settings.auth_enabled,
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
        # Wire defined-but-unwired startup logic (built-in role seed + connector
        # rebuild from the persisted repository) so the platform is usable out
        # of the box and register connectors survive a restart.
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
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready", "env": settings.env}

    return app
