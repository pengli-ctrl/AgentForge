"""模块。"""

from __future__ import annotations

import logging

from agentforge.platform.domain.connector import ConnectorKind
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.modules.demo_asset.api.router import create_asset_router
from agentforge.platform.modules.demo_asset.application.service import AssetService
from agentforge.platform.modules.demo_asset.config import AssetModuleConfig, default_asset_config
from agentforge.platform.modules.demo_asset.infrastructure.memory_repository import (
    MemoryAssetRepository,
)
from agentforge.platform.modules.demo_asset.infrastructure.sqlalchemy_repository import (
    SQLAlchemyAssetRepository,
)
from agentforge.platform.modules.demo_asset.ports import AssetRepository
from agentforge.platform.modules.demo_asset.workflows.asset_workflow import (
    AssetPreparationWorkflow,
    prepare_asset_activity,
)
from agentforge.platform.sdk.connector import ConnectorRegistration
from agentforge.platform.sdk.module import ModuleContext, ModuleManifest, ModuleRuntime

logger = logging.getLogger(__name__)


class DemoAssetModule:
    """演示资产模块领域组件。"""

    manifest = ModuleManifest(
        name="asset",
        version="0.1.0",
        api_prefix="/v1/assets",
        task_queue="asset-copilot",
        migration_namespace="asset",
        depends_on=(
            "core.tenant",
            "core.audit",
            "core.outbox",
        ),
        permissions=(
            "asset.asset.read",
            "asset.asset.write",
        ),
        published_events=("asset.asset.created.v1",),
        consumed_events=("asset.asset.created.v1",),
        enabled_by_default=True,
        config_schema=AssetModuleConfig,
        config_defaults=default_asset_config().model_dump(mode="json"),
        minimum_platform_version="3.1.0",
    )

    def __init__(self, repository: AssetRepository | None = None) -> None:
        """初始化 DemoAssetModule。

        Args:
            repository: 数据仓储实现。
        """
        self._repository = repository

    def build(self, ctx: ModuleContext) -> ModuleRuntime:
        """构建演示资产模块。

        Args:
            ctx: 执行上下文。

        Returns:
            模块运行时结果。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        if ctx.authenticator is None:
            raise RuntimeError("authenticator port is required by the asset module")
        repository = self._repository
        if repository is None:
            if ctx.persistence is None:
                repository = MemoryAssetRepository()
            else:
                repository = SQLAlchemyAssetRepository(ctx.persistence.session_factory_for("asset"))
        service = AssetService(repository, ctx.audit, ctx.outbox)

        async def startup() -> None:
            """启动组件。"""
            logger.info("demo asset module ready")

        async def handle_created(event: EventEnvelope) -> None:
            """处理创建。

            Args:
                event: 待处理事件。
            """
            await service.handle_created_event(event)

        return ModuleRuntime(
            router=create_asset_router(
                service,
                authenticator=ctx.authenticator,
                module_access=ctx.module_access,
            ),
            temporal_workflows=[AssetPreparationWorkflow],
            temporal_activities=[prepare_asset_activity],
            connector_registrations=[
                ConnectorRegistration(
                    connector_id="asset-directory",
                    name="Asset Directory",
                    kind=ConnectorKind.OPENAPI,
                    allowed_actions=("lookup", "sync"),
                )
            ],
            event_handlers={"asset.asset.created.v1": handle_created},
            startup_hooks=[startup],
        )


__all__ = ["DemoAssetModule"]
