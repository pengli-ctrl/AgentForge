"""上传模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class UploadSessionStatus(str, Enum):
    """上传会话状态枚举。"""

    OPEN = "open"
    COMPLETED = "completed"
    EXPIRED = "expired"


class UploadedPart(BaseModel):
    """已上传分片相关组件。

    Attributes:
        part_number: 分片。
        size_bytes: 大小。
        sha256: 字段值。
        object_key: 对象键。
    """

    model_config = ConfigDict(extra="forbid")

    part_number: int = Field(ge=1)
    size_bytes: int = Field(gt=0)
    sha256: str
    object_key: str


class UploadSession(BaseModel):
    """上传会话领域组件。

    Attributes:
        upload_id: 上传ID。
        tenant_id: 租户 ID，用于数据隔离。
        owner_module: 模块。
        filename: 字段值。
        content_type: 内容。
        size_bytes: 大小。
        chunk_size: 分块大小。
        total_chunks: 总计分片。
        status: 当前状态。
        expected_sha256: 字段值。
        completed_sha256: 已完成。
        object_key: 对象键。
        parts: 分片。
        created_at: 创建时间。
        updated_at: 更新时间。
        expires_at: 于。
    """

    model_config = ConfigDict(extra="forbid")

    upload_id: str
    tenant_id: str
    owner_module: str
    filename: str
    content_type: str
    size_bytes: int
    chunk_size: int
    total_chunks: int
    status: UploadSessionStatus = UploadSessionStatus.OPEN
    expected_sha256: str | None = None
    completed_sha256: str | None = None
    object_key: str | None = None
    parts: list[UploadedPart] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime


class UploadCompletion(BaseModel):
    """上传完成相关组件。

    Attributes:
        upload_id: 上传ID。
        filename: 字段值。
        content_type: 内容。
        size_bytes: 大小。
        sha256: 字段值。
        object_key: 对象键。
    """

    model_config = ConfigDict(extra="forbid")

    upload_id: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    object_key: str
