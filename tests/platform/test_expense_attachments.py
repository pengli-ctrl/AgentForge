"""测试报销测试模块。"""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.domain.ocr import OcrField, OcrResult
from agentforge.platform.infrastructure.memory_object_store import MemoryObjectStore
from agentforge.platform.infrastructure.s3_object_store import S3ObjectStore
from agentforge.platform.runtime import build_memory_container


class FakeBody:
    """用于测试的模拟请求体。"""

    def __init__(self, data: bytes) -> None:
        """初始化模拟请求体。

        Args:
            data: 待处理数据。
        """
        self._data = data

    def read(self) -> bytes:
        """读取模拟请求体。

        Returns:
            处理结果对象。
        """
        return self._data


class FakeS3Client:
    """用于测试的模拟 S3 客户端。"""

    def __init__(self) -> None:
        """初始化模拟S3。"""
        self.objects: dict[str, bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        """写入对象。

        Args:
            Bucket: 存储桶。
            Key: 键。
            Body: 请求体。
            ContentType: 内容。
        """
        self.objects[f"{Bucket}/{Key}"] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, FakeBody]:
        """获取对象。

        Args:
            Bucket: 存储桶。
            Key: 键。

        Returns:
            结构化结果字典。
        """
        return {"Body": FakeBody(self.objects[f"{Bucket}/{Key}"])}

    def generate_presigned_url(
        self,
        operation: str,
        *,
        Params: dict[str, str],
        ExpiresIn: int,
    ) -> str:
        """生成预签名URL。

        Args:
            operation: 操作。
            Params: 参数。
            ExpiresIn: 在。

        Returns:
            字符串结果。
        """
        return f"https://s3.test/{Params['Bucket']}/{Params['Key']}?expires={ExpiresIn}"


class FakeOcrProvider:
    """供测试使用的模拟 OCR 提供方。"""

    async def extract(self, content: bytes, content_type: str = "") -> OcrResult:
        """提取模拟OCR提供方。

        Args:
            content: 写入内容。
            content_type: 内容 MIME 类型。

        Returns:
            OCR结果结果。
        """
        assert content == b"invoice-bytes"
        assert content_type == "image/png"
        return OcrResult(
            text="invoice",
            provider="fake",
            fields=[OcrField(name="amount", value="88.00", confidence=0.9)],
        )


def _upload(client: TestClient, tenant_id: str = "tenant-1") -> dict:
    """上传附件。

    Args:
        client: 客户端实例。
        tenant_id: 租户 ID，用于数据隔离。

    Returns:
        结构化结果字典。
    """
    response = client.post(
        "/v1/expense/attachments",
        json={
            "tenant_id": tenant_id,
            "filename": "../invoice.png",
            "content_type": "image/png",
            "content_base64": base64.b64encode(b"invoice-bytes").decode("ascii"),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_memory_and_s3_object_store_contracts() -> None:
    """验证记忆及S3对象存储对应的测试场景。"""
    import asyncio

    memory = MemoryObjectStore()
    asyncio.run(memory.put("a/b", b"data", "text/plain"))
    assert asyncio.run(memory.get("a/b")) == b"data"

    client = FakeS3Client()
    s3 = S3ObjectStore(
        endpoint_url="https://s3.test",
        access_key="key",
        secret_key="secret",
        bucket="bucket",
        client=client,
    )
    asyncio.run(s3.put("a/b", b"data", "text/plain"))
    assert asyncio.run(s3.get("a/b")) == b"data"
    assert "expires=60" in asyncio.run(s3.presigned_get_url("a/b", 60))


def test_attachment_upload_download_and_claim_link() -> None:
    """验证附件上传下载及报销单对应的测试场景。"""
    client = TestClient(create_platform_app())
    attachment = _upload(client)
    assert attachment["filename"] == "invoice.png"
    assert attachment["size_bytes"] == len(b"invoice-bytes")

    fetched = client.get(
        f"/v1/expense/attachments/{attachment['attachment_id']}",
        params={"tenant_id": "tenant-1"},
    )
    assert fetched.status_code == 200
    assert fetched.json()["download_url"].startswith("memory://")
    isolated = client.get(
        f"/v1/expense/attachments/{attachment['attachment_id']}",
        params={"tenant_id": "tenant-2"},
    )
    assert isolated.status_code == 404

    claim = client.post(
        "/v1/expense/claims",
        json={
            "tenant_id": "tenant-1",
            "applicant_id": "employee-1",
            "amount_cents": 8800,
            "expense_date": "2026-10-19",
            "category": "meal",
            "idempotency_key": "attachment-claim-1",
            "attachment_ids": [attachment["attachment_id"]],
        },
    )
    assert claim.status_code == 200
    linked = client.get(
        f"/v1/expense/attachments/{attachment['attachment_id']}",
        params={"tenant_id": "tenant-1"},
    ).json()
    assert linked["claim_id"] == claim.json()["claim_id"]


def test_ocr_can_read_uploaded_attachment() -> None:
    """验证OCR可以读取已上传附件对应的测试场景。"""
    app = create_platform_app(build_memory_container(ocr=FakeOcrProvider()))
    client = TestClient(app)
    attachment = _upload(client)
    response = client.post(
        "/v1/expense/extractions",
        json={
            "tenant_id": "tenant-1",
            "attachment_id": attachment["attachment_id"],
        },
    )
    assert response.status_code == 200
    assert response.json()["amount_cents"] == 8800
    assert response.json()["provider"] == "fake"
