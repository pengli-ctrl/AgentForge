"""SQLAlchemy仓储模块。"""

from __future__ import annotations

from datetime import datetime

from agentforge_module_template.domain.asset import Asset, AssetStatus
from sqlalchemy import DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.db.models import utc_now


class AssetRecord(Base):
    """资产记录持久化模型。

    Attributes:
        asset_id: 资产ID。
        tenant_id: 租户 ID，用于数据隔离。
        name: 名称。
        category: 字段值。
        status: 当前状态。
        created_by: 由。
        created_at: 创建时间。
        archived_at: 已归档于。
    """

    __tablename__ = "module_template_assets"

    asset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    category: Mapped[str] = mapped_column(String(64), default="general")
    status: Mapped[str] = mapped_column(String(32), default=AssetStatus.ACTIVE.value)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SQLAlchemyAssetRepository:
    """资产仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyAssetRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save(self, asset: Asset) -> None:
        """保存资产。

        Args:
            asset: 资产。
        """
        async with self._session_factory() as session:
            record = await session.get(AssetRecord, (asset.asset_id, asset.tenant_id))
            if record is None:
                record = AssetRecord(asset_id=asset.asset_id, tenant_id=asset.tenant_id)
                session.add(record)
            record.name = asset.name
            record.category = asset.category
            record.status = asset.status.value
            record.created_by = asset.created_by
            record.created_at = asset.created_at
            record.archived_at = asset.archived_at
            await session.commit()

    async def get(self, tenant_id: str, asset_id: str) -> Asset | None:
        """读取资产。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            asset_id: 资产 ID。

        Returns:
            资产无结果。
        """
        async with self._session_factory() as session:
            record = await session.get(AssetRecord, (asset_id, tenant_id))
            return self._to_domain(record) if record is not None else None

    async def list(self, tenant_id: str, *, limit: int = 100, offset: int = 0) -> list[Asset]:
        """查询资产。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。
            offset: 分页偏移量。

        Returns:
            结果列表。
        """
        statement = (
            select(AssetRecord)
            .where(AssetRecord.tenant_id == tenant_id)
            .order_by(AssetRecord.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        async with self._session_factory() as session:
            records = list((await session.execute(statement)).scalars().all())
        return [self._to_domain(record) for record in records]

    @staticmethod
    def _to_domain(record: AssetRecord) -> Asset:
        """转换领域。

        Args:
            record: 待处理的领域记录。

        Returns:
            资产结果。
        """
        return Asset(
            asset_id=record.asset_id,
            tenant_id=record.tenant_id,
            name=record.name,
            category=record.category,
            status=AssetStatus(record.status),
            created_by=record.created_by,
            created_at=record.created_at,
            archived_at=record.archived_at,
        )


__all__ = ["AssetRecord", "SQLAlchemyAssetRepository"]
