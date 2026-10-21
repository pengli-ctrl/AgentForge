"""记忆上传会话仓储模块。"""

from __future__ import annotations

from copy import deepcopy

from agentforge.platform.domain.upload import UploadSession


class MemoryUploadSessionRepository:
    """上传会话仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryUploadSessionRepository。"""
        self._sessions: dict[str, UploadSession] = {}

    async def save(self, session: UploadSession) -> None:
        """保存上传会话。

        Args:
            session: 当前会话。
        """
        self._sessions[session.upload_id] = deepcopy(session)

    async def get(self, tenant_id: str, upload_id: str) -> UploadSession | None:
        """读取上传会话。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            upload_id: 上传会话 ID。

        Returns:
            上传会话无结果。
        """
        session = self._sessions.get(upload_id)
        if session is None or session.tenant_id != tenant_id:
            return None
        return deepcopy(session)
