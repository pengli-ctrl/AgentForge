"""测试对象存储测试模块。"""

from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import pytest

from agentforge.platform.application.chunked_upload_service import ChunkedUploadService
from agentforge.platform.infrastructure.db.base import create_session_factory
from agentforge.platform.infrastructure.s3_object_store import S3ObjectStore
from agentforge.platform.infrastructure.sqlalchemy_upload_session_repository import (
    SQLAlchemyUploadSessionRepository,
)
from tests.infra.conftest import DATABASE_URL, RUN_INFRA

pytestmark = [
    pytest.mark.infra,
    pytest.mark.skipif(not RUN_INFRA, reason="set AGENTFORGE_RUN_INFRA_TESTS=1"),
]


@pytest.mark.asyncio
async def test_resumable_upload_round_trip_against_minio() -> None:
    """验证可续传上传轮次往返针对对应的测试场景。"""
    store = S3ObjectStore(
        endpoint_url=os.environ.get("AGENTFORGE_OBJECT_STORE_ENDPOINT", "http://localhost:9000"),
        access_key=os.environ.get("AGENTFORGE_OBJECT_STORE_ACCESS_KEY", "agentforge"),
        secret_key=os.environ.get("AGENTFORGE_OBJECT_STORE_SECRET_KEY", "agentforge"),
        bucket=os.environ.get("AGENTFORGE_OBJECT_STORE_BUCKET", "agentforge-infra-test"),
        region=os.environ.get("AGENTFORGE_OBJECT_STORE_REGION", "us-east-1"),
    )
    session_factory = create_session_factory(DATABASE_URL)
    repository = SQLAlchemyUploadSessionRepository(session_factory)
    service = ChunkedUploadService(repository, store)
    content = b"abcdefghij"
    upload = await service.begin(
        tenant_id=f"tenant-{uuid4()}",
        owner_module="infra",
        filename="proof.txt",
        content_type="text/plain",
        size_bytes=len(content),
        chunk_size=6,
        sha256=hashlib.sha256(content).hexdigest(),
    )
    await service.put_part(upload.tenant_id, upload.upload_id, 2, content[6:])

    resumed_service = ChunkedUploadService(
        SQLAlchemyUploadSessionRepository(session_factory),
        store,
    )
    resumed = await resumed_service.get(upload.tenant_id, upload.upload_id)
    assert [part.part_number for part in resumed.parts] == [2]
    await resumed_service.put_part(upload.tenant_id, upload.upload_id, 1, content[:6])
    completed = await resumed_service.complete(upload.tenant_id, upload.upload_id)

    assert await store.get(completed.object_key) == content
    assert "X-Amz-Signature" in await store.presigned_get_url(completed.object_key, 60)
    part_key = f"tenants/{upload.tenant_id}/modules/infra/uploads/{upload.upload_id}/parts/1"
    with pytest.raises(Exception):
        await store.get(part_key)

    await store.delete(completed.object_key)
    with pytest.raises(Exception):
        await store.get(completed.object_key)
