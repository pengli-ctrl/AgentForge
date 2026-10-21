"""测试报销可续传上传测试模块。"""

from __future__ import annotations

import asyncio
import base64
import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.application.chunked_upload_service import ChunkedUploadService
from agentforge.platform.domain.upload import UploadSessionStatus
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.memory_object_store import MemoryObjectStore
from agentforge.platform.infrastructure.sqlalchemy_upload_session_repository import (
    SQLAlchemyUploadSessionRepository,
)
from agentforge.platform.runtime import build_memory_container


def _begin_upload(
    client: TestClient,
    data: bytes,
    *,
    tenant_id: str = "tenant-upload",
    chunk_size: int = 8,
    sha256: str | None = None,
) -> dict:
    """开始上传。

    Args:
        client: 客户端实例。
        data: 待处理数据。
        tenant_id: 租户 ID，用于数据隔离。
        chunk_size: 分块大小。
        sha256: 输入参数。

    Returns:
        结构化结果字典。
    """
    response = client.post(
        "/v1/expense/upload-sessions",
        json={
            "tenant_id": tenant_id,
            "filename": "archive.pdf",
            "content_type": "application/pdf",
            "size_bytes": len(data),
            "chunk_size": chunk_size,
            "sha256": sha256 or hashlib.sha256(data).hexdigest(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _put_part(
    client: TestClient,
    upload_id: str,
    part_number: int,
    data: bytes,
    *,
    tenant_id: str = "tenant-upload",
    sha256: str | None = None,
) -> dict:
    """写入分片。

    Args:
        client: 客户端实例。
        upload_id: 上传会话 ID。
        part_number: 分片。
        data: 待处理数据。
        tenant_id: 租户 ID，用于数据隔离。
        sha256: 输入参数。

    Returns:
        结构化结果字典。
    """
    response = client.put(
        f"/v1/expense/upload-sessions/{upload_id}/parts/{part_number}",
        json={
            "tenant_id": tenant_id,
            "content_base64": base64.b64encode(data).decode(),
            "sha256": sha256,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_resumable_upload_assembles_out_of_order_parts_and_registers_attachment() -> None:
    """验证可续传上传排序分片及注册附件对应的测试场景。"""
    object_store = MemoryObjectStore()
    container = build_memory_container(object_store=object_store)
    client = TestClient(create_platform_app(container))
    content = b"hello resumable upload"

    session = _begin_upload(client, content)
    assert session["total_chunks"] == 3
    assert session["received_chunks"] == 0

    second = _put_part(client, session["upload_id"], 2, content[8:16])
    assert second["received_chunks"] == 1
    first = _put_part(client, session["upload_id"], 1, content[:8])
    assert first["progress"] == round(16 / len(content), 4)
    _put_part(client, session["upload_id"], 3, content[16:])

    completed = client.post(
        f"/v1/expense/upload-sessions/{session['upload_id']}/complete",
        json={"tenant_id": "tenant-upload"},
    )
    assert completed.status_code == 200, completed.text
    body = completed.json()
    assert body["upload"]["status"] == UploadSessionStatus.COMPLETED.value
    assert body["upload"]["progress"] == 1.0
    assert body["attachment"]["attachment_id"] == session["upload_id"]
    assert body["attachment"]["size_bytes"] == len(content)
    assert body["attachment"]["sha256"] == hashlib.sha256(content).hexdigest()

    attachment = client.get(
        f"/v1/expense/attachments/{body['attachment']['attachment_id']}",
        params={"tenant_id": "tenant-upload"},
    )
    assert attachment.status_code == 200
    assert attachment.json()["download_url"].startswith("memory://")
    assert asyncio.run(object_store.get(body["attachment"]["object_key"])) == content
    assert not any("/parts/" in key for key in object_store.objects)


def test_resumable_upload_rejects_bad_hash_and_incomplete_completion() -> None:
    """验证可续传上传拒绝异常哈希及完成对应的测试场景。"""
    client = TestClient(create_platform_app(build_memory_container()))
    content = b"0123456789abcdef"
    session = _begin_upload(client, content, chunk_size=8)

    bad_hash = client.put(
        f"/v1/expense/upload-sessions/{session['upload_id']}/parts/1",
        json={
            "tenant_id": "tenant-upload",
            "content_base64": base64.b64encode(content[:8]).decode(),
            "sha256": "0" * 64,
        },
    )
    assert bad_hash.status_code == 422
    state = client.get(
        f"/v1/expense/upload-sessions/{session['upload_id']}",
        params={"tenant_id": "tenant-upload"},
    ).json()
    assert state["received_chunks"] == 0

    _put_part(client, session["upload_id"], 1, content[:8])
    incomplete = client.post(
        f"/v1/expense/upload-sessions/{session['upload_id']}/complete",
        json={"tenant_id": "tenant-upload"},
    )
    assert incomplete.status_code == 409
    assert "missing part" in incomplete.json()["detail"]

    mismatch = _begin_upload(client, content, chunk_size=8, sha256="0" * 64)
    _put_part(client, mismatch["upload_id"], 1, content[:8])
    _put_part(client, mismatch["upload_id"], 2, content[8:])
    mismatch_complete = client.post(
        f"/v1/expense/upload-sessions/{mismatch['upload_id']}/complete",
        json={"tenant_id": "tenant-upload"},
    )
    assert mismatch_complete.status_code == 409
    assert "sha256" in mismatch_complete.json()["detail"]


def test_resumable_upload_is_tenant_isolated_and_complete_is_idempotent() -> None:
    """验证可续传上传是否租户隔离及完成是否幂等对应的测试场景。"""
    container = build_memory_container()
    client = TestClient(create_platform_app(container))
    content = b"tenant isolated upload"
    session = _begin_upload(client, content, chunk_size=10)

    isolated = client.get(
        f"/v1/expense/upload-sessions/{session['upload_id']}",
        params={"tenant_id": "tenant-other"},
    )
    assert isolated.status_code == 404

    for part_number, offset in enumerate(range(0, len(content), 10), start=1):
        _put_part(
            client,
            session["upload_id"],
            part_number,
            content[offset : offset + 10],
        )
    first = client.post(
        f"/v1/expense/upload-sessions/{session['upload_id']}/complete",
        json={"tenant_id": "tenant-upload"},
    )
    second = client.post(
        f"/v1/expense/upload-sessions/{session['upload_id']}/complete",
        json={"tenant_id": "tenant-upload"},
    )
    assert first.status_code == 200 and second.status_code == 200
    assert (
        first.json()["attachment"]["attachment_id"] == second.json()["attachment"]["attachment_id"]
    )

    audit = client.get(
        "/v1/audit",
        params={"tenant_id": "tenant-upload", "resource_id": session["upload_id"]},
    ).json()["events"]
    assert len(audit) == 1
    assert audit[0]["action"] == "expense.attachment.uploaded"


@pytest.mark.asyncio
async def test_sqlalchemy_upload_session_round_trip() -> None:
    """验证SQLAlchemy上传会话轮次往返对应的测试场景。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = SQLAlchemyUploadSessionRepository(session_factory)
    service = ChunkedUploadService(repository, MemoryObjectStore())

    session = await service.begin(
        tenant_id="tenant-sql-upload",
        owner_module="expense",
        filename="large.pdf",
        content_type="application/pdf",
        size_bytes=4,
        chunk_size=2,
        sha256=hashlib.sha256(b"test").hexdigest(),
    )
    await service.put_part("tenant-sql-upload", session.upload_id, 1, b"te")
    await service.put_part("tenant-sql-upload", session.upload_id, 2, b"st")
    completion = await service.complete("tenant-sql-upload", session.upload_id)
    stored = await repository.get("tenant-sql-upload", session.upload_id)

    assert completion.sha256 == hashlib.sha256(b"test").hexdigest()
    assert stored is not None
    assert stored.status == UploadSessionStatus.COMPLETED
    assert len(stored.parts) == 2
    await engine.dispose()
