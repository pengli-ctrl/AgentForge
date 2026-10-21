"""上传服务模块。"""

from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import PurePath
from uuid import uuid4

from agentforge.platform.application.ports import UploadSessionRepository
from agentforge.platform.domain.upload import (
    UploadCompletion,
    UploadedPart,
    UploadSession,
    UploadSessionStatus,
)
from agentforge.platform.domain.usage import UsageMetric
from agentforge.platform.sdk.ports import ObjectStorePort, UsagePort

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_CHUNK_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_CHUNKS = 1000
UPLOAD_SESSION_TTL = timedelta(hours=24)
_MODULE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ChunkedUploadService:
    """上传应用服务，编排领域用例及其副作用。"""

    def __init__(
        self,
        repository: UploadSessionRepository,
        object_store: ObjectStorePort,
        usage: UsagePort | None = None,
    ) -> None:
        """初始化 ChunkedUploadService。

        Args:
            repository: 数据仓储实现。
            object_store: 对象存储。
            usage: 用量统计数据。
        """
        self._repository = repository
        self._object_store = object_store
        self._usage = usage

    def set_usage_meter(self, usage: UsagePort) -> None:
        """设置用量计量。

        Args:
            usage: 用量统计数据。
        """
        self._usage = usage

    async def begin(
        self,
        *,
        tenant_id: str,
        owner_module: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        chunk_size: int,
        sha256: str | None = None,
    ) -> UploadSession:
        """开始上传。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            owner_module: 模块。
            filename: 输入参数。
            content_type: 内容 MIME 类型。
            size_bytes: 大小。
            chunk_size: 分块大小。
            sha256: 输入参数。

        Returns:
            上传会话结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if not tenant_id.strip():
            raise ValueError("tenant_id is required")
        if not _MODULE_NAME.fullmatch(owner_module):
            raise ValueError("owner_module must be a valid module name")
        if size_bytes < 1 or size_bytes > MAX_UPLOAD_BYTES:
            raise ValueError("size_bytes must be between 1 and 100 MB")
        if chunk_size < 1 or chunk_size > MAX_CHUNK_BYTES:
            raise ValueError("chunk_size must be between 1 byte and 10 MB")
        total_chunks = math.ceil(size_bytes / chunk_size)
        if total_chunks > MAX_UPLOAD_CHUNKS:
            raise ValueError("upload would exceed 1000 chunks")

        safe_name = PurePath(filename).name or "attachment"
        normalized_content_type = content_type.strip() or "application/octet-stream"
        expected_sha256 = _normalize_sha256(sha256)
        now = datetime.now(timezone.utc)
        session = UploadSession(
            upload_id=str(uuid4()),
            tenant_id=tenant_id,
            owner_module=owner_module,
            filename=safe_name,
            content_type=normalized_content_type,
            size_bytes=size_bytes,
            chunk_size=chunk_size,
            total_chunks=total_chunks,
            expected_sha256=expected_sha256,
            created_at=now,
            updated_at=now,
            expires_at=now + UPLOAD_SESSION_TTL,
        )
        await self._repository.save(session)
        return session

    async def get(self, tenant_id: str, upload_id: str) -> UploadSession:
        """获取上传。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            upload_id: 上传会话 ID。

        Returns:
            上传会话结果。

        Raises:
            LookupError: 操作无法完成时抛出。
        """
        session = await self._repository.get(tenant_id, upload_id)
        if session is None:
            raise LookupError("upload session not found")
        if session.status == UploadSessionStatus.OPEN and session.expires_at <= datetime.now(
            timezone.utc
        ):
            session.status = UploadSessionStatus.EXPIRED
            session.updated_at = datetime.now(timezone.utc)
            await self._repository.save(session)
            await self._delete_parts(session)
        return session

    async def put_part(
        self,
        tenant_id: str,
        upload_id: str,
        part_number: int,
        data: bytes,
        sha256: str | None = None,
    ) -> UploadSession:
        """写入分片。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            upload_id: 上传会话 ID。
            part_number: 分片。
            data: 待处理数据。
            sha256: 输入参数。

        Returns:
            上传会话结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        session = await self._require_open_session(tenant_id, upload_id)
        if part_number < 1 or part_number > session.total_chunks:
            raise ValueError("part_number is outside the upload range")
        expected_size = _part_size(session, part_number)
        if len(data) != expected_size:
            raise ValueError(f"part {part_number} must contain exactly {expected_size} bytes")
        part_sha256 = hashlib.sha256(data).hexdigest()
        supplied_sha256 = _normalize_sha256(sha256)
        if supplied_sha256 is not None and supplied_sha256 != part_sha256:
            raise ValueError("part sha256 does not match content")

        object_key = _part_key(session, part_number)
        await self._object_store.put(object_key, data, "application/octet-stream")
        part = UploadedPart(
            part_number=part_number,
            size_bytes=len(data),
            sha256=part_sha256,
            object_key=object_key,
        )
        session.parts = [
            existing for existing in session.parts if existing.part_number != part_number
        ]
        session.parts.append(part)
        session.parts.sort(key=lambda item: item.part_number)
        session.updated_at = datetime.now(timezone.utc)
        await self._repository.save(session)
        return session

    async def complete(self, tenant_id: str, upload_id: str) -> UploadCompletion:
        """完成上传。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            upload_id: 上传会话 ID。

        Returns:
            上传完成结果。

        Raises:
            LookupError: 操作无法完成时抛出。
            ValueError: 输入值或业务状态不合法时抛出。
        """
        session = await self._repository.get(tenant_id, upload_id)
        if session is None:
            raise LookupError("upload session not found")
        if session.status == UploadSessionStatus.COMPLETED:
            return _completion(session)
        session = await self._require_open_session(tenant_id, upload_id)
        if len(session.parts) != session.total_chunks:
            missing = session.total_chunks - len(session.parts)
            raise ValueError(f"upload has {missing} missing part(s)")

        content = b"".join(
            [await self._object_store.get(part.object_key) for part in session.parts]
        )
        if len(content) != session.size_bytes:
            raise ValueError("assembled upload size does not match session")
        completed_sha256 = hashlib.sha256(content).hexdigest()
        if session.expected_sha256 is not None and session.expected_sha256 != completed_sha256:
            raise ValueError("assembled upload sha256 does not match session")

        object_key = _final_key(session)
        await self._object_store.put(object_key, content, session.content_type)
        session.status = UploadSessionStatus.COMPLETED
        session.completed_sha256 = completed_sha256
        session.object_key = object_key
        session.updated_at = datetime.now(timezone.utc)
        await self._repository.save(session)
        await self._delete_parts(session)
        if self._usage is not None:
            await self._usage.record(
                tenant_id=session.tenant_id,
                metric=UsageMetric.STORAGE_BYTES,
                quantity=session.size_bytes,
                source=f"{session.owner_module}-upload",
                idempotency_key=f"storage:{session.upload_id}",
                metadata={"owner_module": session.owner_module},
            )
        return _completion(session)

    async def _require_open_session(self, tenant_id: str, upload_id: str) -> UploadSession:
        """处理要求打开会话。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            upload_id: 上传会话 ID。

        Returns:
            上传会话结果。

        Raises:
            LookupError: 操作无法完成时抛出。
            ValueError: 输入值或业务状态不合法时抛出。
        """
        session = await self._repository.get(tenant_id, upload_id)
        if session is None:
            raise LookupError("upload session not found")
        if session.status == UploadSessionStatus.COMPLETED:
            raise ValueError("upload session is already completed")
        if session.status == UploadSessionStatus.EXPIRED or session.expires_at <= datetime.now(
            timezone.utc
        ):
            if session.status != UploadSessionStatus.EXPIRED:
                session.status = UploadSessionStatus.EXPIRED
                session.updated_at = datetime.now(timezone.utc)
                await self._repository.save(session)
                await self._delete_parts(session)
            raise ValueError("upload session has expired")
        return session

    async def _delete_parts(self, session: UploadSession) -> None:
        """删除分片。

        Args:
            session: 当前会话。
        """
        for part in session.parts:
            try:
                await self._object_store.delete(part.object_key)
            except Exception:  # noqa: BLE001 - cleanup must not corrupt session state
                continue


def _part_size(session: UploadSession, part_number: int) -> int:
    """处理分片大小。

    Args:
        session: 当前会话。
        part_number: 分片。

    Returns:
        整数结果。
    """
    if part_number < session.total_chunks:
        return session.chunk_size
    return session.size_bytes - session.chunk_size * (session.total_chunks - 1)


def _part_key(session: UploadSession, part_number: int) -> str:
    """处理分片键。

    Args:
        session: 当前会话。
        part_number: 分片。

    Returns:
        字符串结果。
    """
    return (
        f"tenants/{session.tenant_id}/modules/{session.owner_module}/uploads/"
        f"{session.upload_id}/parts/{part_number}"
    )


def _final_key(session: UploadSession) -> str:
    """处理最终键。

    Args:
        session: 当前会话。

    Returns:
        字符串结果。
    """
    return (
        f"tenants/{session.tenant_id}/modules/{session.owner_module}/uploads/"
        f"{session.upload_id}/content"
    )


def _completion(session: UploadSession) -> UploadCompletion:
    """构建上传完成结果。

    Args:
        session: 当前会话。

    Returns:
        上传完成结果。

    Raises:
        ValueError: 输入值或业务状态不合法时抛出。
    """
    if session.object_key is None or session.completed_sha256 is None:
        raise ValueError("upload session has no completed object")
    return UploadCompletion(
        upload_id=session.upload_id,
        filename=session.filename,
        content_type=session.content_type,
        size_bytes=session.size_bytes,
        sha256=session.completed_sha256,
        object_key=session.object_key,
    )


def _normalize_sha256(value: str | None) -> str | None:
    """规范化数据。

    Args:
        value: 待处理值。

    Returns:
        无结果。

    Raises:
        ValueError: 输入值或业务状态不合法时抛出。
    """
    if value is None or not value.strip():
        return None
    normalized = value.strip().lower()
    if not _SHA256.fullmatch(normalized):
        raise ValueError("sha256 must be a 64-character hexadecimal string")
    return normalized
