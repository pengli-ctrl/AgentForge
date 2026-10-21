"""服务模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from agentforge_module_template.domain.asset import Asset, AssetStatus
from agentforge_module_template.ports import AssetRepository

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.risk import RiskLevel
from agentforge.platform.sdk.ports import AuditPort, OutboxPort


class AssetService:
    """资产应用服务，编排领域用例及其副作用。"""

    def __init__(self, repository: AssetRepository, audit: AuditPort, outbox: OutboxPort) -> None:
        """初始化 AssetService。

        Args:
            repository: 数据仓储实现。
            audit: 审计。
            outbox: Outbox。
        """
        self._repository = repository
        self._audit = audit
        self._outbox = outbox
        self._observed_events: set[str] = set()

    async def create(
        self,
        *,
        tenant_id: str,
        name: str,
        created_by: str,
        category: str = "general",
    ) -> Asset:
        """创建资产。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            name: 资源或对象名称。
            created_by: 由。
            category: 输入参数。

        Returns:
            资产结果。
        """
        self._require(tenant_id, "tenant_id")
        self._require(name, "name")
        self._require(created_by, "created_by")
        asset = Asset(
            asset_id=str(uuid4()),
            tenant_id=tenant_id,
            name=name.strip(),
            category=category.strip() or "general",
            created_by=created_by.strip(),
        )
        await self._repository.save(asset)
        trace_id = str(uuid4())
        await self._audit.save(
            AuditEvent(
                event_id=str(uuid4()),
                tenant_id=tenant_id,
                action="asset.created",
                resource_type="asset",
                resource_id=asset.asset_id,
                risk_level=RiskLevel.LOW,
                actor_type="user",
                actor_id=asset.created_by,
                trace_id=trace_id,
                payload={"name": asset.name, "category": asset.category},
            )
        )
        await self._outbox.enqueue(
            EventEnvelope(
                event_id=str(uuid4()),
                event_type="asset.asset.created.v1",
                tenant_id=tenant_id,
                task_id=asset.asset_id,
                trace_id=trace_id,
                producer="demo-asset",
                payload=asset.model_dump(mode="json"),
            )
        )
        return asset

    async def get(self, tenant_id: str, asset_id: str) -> Asset | None:
        """读取资产。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            asset_id: 资产 ID。

        Returns:
            资产无结果。
        """
        self._require(tenant_id, "tenant_id")
        return await self._repository.get(tenant_id, asset_id)

    async def list(self, tenant_id: str, *, limit: int = 100, offset: int = 0) -> list[Asset]:
        """查询资产。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。
            offset: 分页偏移量。

        Returns:
            结果列表。
        """
        self._require(tenant_id, "tenant_id")
        return await self._repository.list(tenant_id, limit=max(1, min(limit, 500)), offset=offset)

    async def archive(self, tenant_id: str, asset_id: str) -> Asset | None:
        """执行归档。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            asset_id: 资产 ID。

        Returns:
            资产无结果。
        """
        asset = await self.get(tenant_id, asset_id)
        if asset is None:
            return None
        asset.status = AssetStatus.ARCHIVED
        asset.archived_at = datetime.now(timezone.utc)
        await self._repository.save(asset)
        return asset

    async def handle_created_event(self, event: EventEnvelope) -> None:
        """处理创建事件。

        Args:
            event: 待处理事件。
        """
        self._observed_events.add(event.event_id)
        await self._audit.save(
            AuditEvent(
                event_id=str(uuid4()),
                tenant_id=event.tenant_id,
                action="asset.event.observed",
                resource_type="asset",
                resource_id=str(event.payload.get("asset_id") or event.task_id),
                actor_type="system",
                actor_id="demo-asset-handler",
                trace_id=event.trace_id,
                payload={"event_type": event.event_type},
            )
        )

    @staticmethod
    def _require(value: str, field: str) -> None:
        """执行校验。

        Args:
            value: 待处理值。
            field: 字段。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if not value.strip():
            raise ValueError(f"{field} is required")


__all__ = ["AssetService"]
