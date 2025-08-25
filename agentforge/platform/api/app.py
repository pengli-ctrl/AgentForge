from __future__ import annotations

from fastapi import FastAPI

from agentforge.platform.api.audit_router import create_audit_router
from agentforge.platform.api.connector_router import create_connector_router
from agentforge.platform.api.cost_router import create_cost_router
from agentforge.platform.api.evaluation_router import create_evaluation_router
from agentforge.platform.api.feishu_router import create_feishu_router
from agentforge.platform.api.knowledge_router import create_knowledge_router
from agentforge.platform.api.outbox_router import create_outbox_router
from agentforge.platform.api.regression_router import create_regression_router
from agentforge.platform.api.release_router import create_release_router
from agentforge.platform.api.security import ApiKeyAuthenticator
from agentforge.platform.api.support_router import create_support_router
from agentforge.platform.infrastructure.db.base import create_session_factory
from agentforge.platform.infrastructure.feishu_reply_connector import FeishuReplyConnector
from agentforge.platform.infrastructure.temporal.client import TemporalWorkflowClient
from agentforge.platform.runtime import (
    ServiceContainer,
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

    app = FastAPI(title="AgentForge Platform", version="0.5.0")
    app.include_router(create_support_router(container))
    app.include_router(create_knowledge_router(container))
    app.include_router(create_outbox_router(container))
    app.include_router(create_audit_router(container))
    app.include_router(create_cost_router(container))
    app.include_router(create_evaluation_router(container))
    app.include_router(create_release_router(container))
    app.include_router(create_regression_router(container))
    app.include_router(create_connector_router(container.connector_registry))
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
        )
    )

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready", "env": settings.env}

    return app
