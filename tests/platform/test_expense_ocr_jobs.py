"""测试报销OCR任务测试模块。"""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.domain.ocr import OcrField, OcrResult
from agentforge.platform.runtime import build_memory_container


class FakeWorkflowClient:
    """记录工作流调用的测试客户端。"""

    def __init__(self) -> None:
        """初始化模拟。"""
        self.calls: list[dict] = []

    async def start_workflow(self, workflow, arg, **kwargs):
        """启动工作流。

        Args:
            workflow: 工作流定义或实例。
            arg: 输入参数。
            kwargs: 关键字参数。

        Returns:
            处理结果。
        """
        self.calls.append({"workflow": workflow, "arg": arg, **kwargs})
        return kwargs.get("workflow_id") or "workflow-1"

    async def signal_workflow(self, workflow_id, signal, arg=None) -> None:
        """发送信号工作流。

        Args:
            workflow_id: 工作流 ID。
            signal: 信号。
            arg: 输入参数。
        """
        return None


class FlakyOcrProvider:
    """不稳定OCR提供方相关组件。"""

    def __init__(self) -> None:
        """初始化不稳定OCR提供方。"""
        self.calls = 0

    async def extract(self, content: bytes, content_type: str = "") -> OcrResult:
        """提取不稳定OCR提供方。

        Args:
            content: 写入内容。
            content_type: 内容 MIME 类型。

        Returns:
            OCR结果结果。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary OCR failure")
        return OcrResult(
            text="invoice",
            provider="flaky",
            fields=[OcrField(name="amount", value="10.00", confidence=0.9)],
        )


def _upload(client: TestClient, key: str, tenant_id: str = "tenant-job") -> str:
    """上传附件。

    Args:
        client: 客户端实例。
        key: 缓存或配置键。
        tenant_id: 租户 ID，用于数据隔离。

    Returns:
        字符串结果。
    """
    response = client.post(
        "/v1/expense/attachments",
        json={
            "tenant_id": tenant_id,
            "filename": f"{key}.png",
            "content_type": "image/png",
            "content_base64": base64.b64encode(key.encode()).decode(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["attachment_id"]


def test_ocr_job_batch_and_tenant_isolation() -> None:
    """验证OCR任务批次及租户隔离对应的测试场景。"""
    provider = FlakyOcrProvider()
    provider.calls = 1
    client = TestClient(create_platform_app(build_memory_container(ocr=provider)))
    ids = [_upload(client, "one"), _upload(client, "two")]
    response = client.post(
        "/v1/expense/ocr-jobs/batch",
        json={"tenant_id": "tenant-job", "attachment_ids": ids},
    )
    assert response.status_code == 200, response.text
    jobs = response.json()["jobs"]
    assert [job["status"] for job in jobs] == ["succeeded", "succeeded"]
    assert all(job["extraction_id"] for job in jobs)

    listed = client.get("/v1/expense/ocr-jobs", params={"tenant_id": "tenant-job"}).json()
    assert len(listed["jobs"]) == 2
    summary = client.get(
        "/v1/expense/ocr-jobs/summary",
        params={"tenant_id": "tenant-job"},
    ).json()
    assert summary["total"] == 2
    assert summary["by_status"]["succeeded"] == 2
    assert summary["success_rate"] == 1.0
    one = client.get(
        f"/v1/expense/ocr-jobs/{jobs[0]['job_id']}",
        params={"tenant_id": "tenant-job"},
    )
    assert one.status_code == 200
    isolated = client.get(
        f"/v1/expense/ocr-jobs/{jobs[0]['job_id']}",
        params={"tenant_id": "tenant-other"},
    )
    assert isolated.status_code == 404


def test_failed_ocr_job_can_be_retried() -> None:
    """验证失败OCR任务可以为已重试对应的测试场景。"""
    provider = FlakyOcrProvider()
    client = TestClient(create_platform_app(build_memory_container(ocr=provider)))
    attachment_id = _upload(client, "retry")
    queued = client.post(
        "/v1/expense/ocr-jobs",
        json={"tenant_id": "tenant-job", "attachment_id": attachment_id},
    )
    assert queued.status_code == 200
    assert queued.json()["status"] == "failed"
    assert "temporary OCR failure" in queued.json()["error"]

    retried = client.post(
        f"/v1/expense/ocr-jobs/{queued.json()['job_id']}/retry",
        json={"tenant_id": "tenant-job"},
    )
    assert retried.status_code == 200
    assert retried.json()["status"] == "succeeded"
    assert retried.json()["attempts"] == 2
    assert retried.json()["extraction_id"]


def test_batch_import_uploads_and_enqueues_documents() -> None:
    """验证批次导入上传及文档对应的测试场景。"""
    provider = FlakyOcrProvider()
    provider.calls = 1
    client = TestClient(create_platform_app(build_memory_container(ocr=provider)))
    response = client.post(
        "/v1/expense/imports",
        json={
            "tenant_id": "tenant-import",
            "files": [
                {
                    "filename": "a.png",
                    "content_type": "image/png",
                    "content_base64": base64.b64encode(b"a").decode(),
                },
                {
                    "filename": "b.png",
                    "content_type": "image/png",
                    "content_base64": base64.b64encode(b"b").decode(),
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["total_files"] == 2
    assert body["success_count"] == 2
    assert len(body["items"]) == 2
    assert all(item["job_id"] for item in body["items"])

    listed = client.get("/v1/expense/imports", params={"tenant_id": "tenant-import"}).json()
    assert len(listed["batches"]) == 1
    detail = client.get(
        f"/v1/expense/imports/{body['batch_id']}",
        params={"tenant_id": "tenant-import"},
    )
    assert detail.status_code == 200
    assert detail.json()["batch_id"] == body["batch_id"]


def test_ocr_job_dispatches_to_expense_temporal_queue() -> None:
    """验证OCR任务分发到报销Temporal队列对应的测试场景。"""
    provider = FlakyOcrProvider()
    provider.calls = 1
    workflow_client = FakeWorkflowClient()
    container = build_memory_container(
        ocr=provider,
        workflow_client=workflow_client,
    )
    client = TestClient(create_platform_app(container))
    attachment_id = _upload(client, "async")
    response = client.post(
        "/v1/expense/ocr-jobs",
        json={"tenant_id": "tenant-job", "attachment_id": attachment_id},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    assert workflow_client.calls[0]["task_queue"] == "expense-copilot"
    assert workflow_client.calls[0]["arg"]["tenant_id"] == "tenant-job"


def test_failed_import_batch_can_retry_failed_items() -> None:
    """验证失败导入批次可以重试失败条目对应的测试场景。"""
    provider = FlakyOcrProvider()
    client = TestClient(create_platform_app(build_memory_container(ocr=provider)))
    response = client.post(
        "/v1/expense/imports",
        json={
            "tenant_id": "tenant-retry-import",
            "files": [
                {
                    "filename": "a.png",
                    "content_type": "image/png",
                    "content_base64": base64.b64encode(b"a").decode(),
                },
                {
                    "filename": "b.png",
                    "content_type": "image/png",
                    "content_base64": base64.b64encode(b"b").decode(),
                },
            ],
        },
    )
    assert response.status_code == 200
    batch = response.json()
    assert batch["status"] == "partial_failed"
    assert batch["failed_count"] == 1

    retried = client.post(
        f"/v1/expense/imports/{batch['batch_id']}/retry-failed",
        json={"tenant_id": "tenant-retry-import"},
    )
    assert retried.status_code == 200
    assert retried.json()["status"] == "completed"
    assert retried.json()["failed_count"] == 0
