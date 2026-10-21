"""SQLAlchemy上传会话仓储模块。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.upload import UploadSession
from agentforge.platform.infrastructure.db.models import UploadSessionRecord


class SQLAlchemyUploadSessionRepository:
    """上传会话仓储，负责持久化读写。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyUploadSessionRepository。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    async def save(self, session: UploadSession) -> None:
        """保存上传会话。

        Args:
            session: 当前会话。
        """
        async with self._session_factory() as db:
            row = await db.get(UploadSessionRecord, session.upload_id)
            if row is None:
                db.add(UploadSessionRecord.from_domain(session))
            else:
                row.apply_domain(session)
            await db.commit()

    async def get(self, tenant_id: str, upload_id: str) -> UploadSession | None:
        """读取上传会话。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            upload_id: 上传会话 ID。

        Returns:
            上传会话无结果。
        """
        async with self._session_factory() as db:
            row = await db.get(UploadSessionRecord, upload_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return row.to_domain()
