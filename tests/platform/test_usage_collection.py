"""测试用量测试模块。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.application.chunked_upload_service import ChunkedUploadService
from agentforge.platform.application.quota_service import QuotaAwareModelGateway
from agentforge.platform.application.usage_metering_service import UsageMeteringAdapter
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.model import ModelRequest, ModelResponse
from agentforge.platform.domain.ocr import OcrField, OcrResult
from agentforge.platform.domain.priority import PriorityLevel
from agentforge.platform.domain.usage import UsageMetric
from agentforge.platform.infrastructure.memory_cost_repository import MemoryCostRepository
from agentforge.platform.infrastructure.memory_object_store import MemoryObjectStore
from agentforge.platform.infrastructure.memory_upload_session_repository import (
    MemoryUploadSessionRepository,
)
from agentforge.platform.infrastructure.temporal.client import TemporalWorkflowClient
from agentforge.platform.modules.expense.application.ocr_extraction_service import ExpenseOcrService
from agentforge.platform.modules.expense.infrastructure.memory_extraction_repository import (
    MemoryExpenseExtractionRepository,
)
from agentforge.platform.modules.support.application.notification import SupportNotificationService
from agentforge.platform.modules.support.domain.ticket import Ticket, TicketStatus
from agentforge.platform.modules.support.infrastructure.memory_notification_gateway import (
    MemoryNotificationGateway,
)
from agentforge.platform.modules.support.infrastructure.memory_repository import (
    MemoryTicketRepository,
)


class RecordingUsage:
    """记录用量相关组件。"""

    def __init__(self) -> None:
        """初始化记录用量。"""
        self.records: list[dict] = []

    async def record(self, **kwargs) -> None:
        """记录用量。

        Args:
            kwargs: 关键字参数。
        """
        self.records.append(kwargs)


class StaticInnerGateway:
    """静态网关抽象。"""

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """完成静态。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            模型响应结果。
        """
        return ModelResponse(
            content="ok",
            model="static",
            provider="local",
            input_tokens=12,
            output_tokens=5,
        )


class FakeOcr:
    """用于测试的模拟OCR。"""

    async def extract(self, content: bytes, content_type: str = "") -> OcrResult:
        """提取模拟OCR。

        Args:
            content: 写入内容。
            content_type: 内容 MIME 类型。

        Returns:
            OCR结果结果。
        """
        return OcrResult(
            text="invoice",
            provider="fake-ocr",
            metadata={"page_count": 3},
            fields=[OcrField(name="amount", value="12.34", confidence=0.9)],
        )


@pytest.mark.asyncio
async def test_model_gateway_records_tenant_tokens() -> None:
    """验证模型网关记录租户对应的测试场景。"""
    usage = RecordingUsage()
    gateway = QuotaAwareModelGateway(
        StaticInnerGateway(),
        cost_repository=MemoryCostRepository(),
        monthly_budget=100,
    )
    gateway.set_usage_meter(usage)
    await gateway.complete(
        ModelRequest(
            system_prompt="s",
            user_prompt="u",
            metadata={"tenant_id": "tenant-meter", "trace_id": "trace-model-1"},
        )
    )
    assert usage.records[0]["metric"] == UsageMetric.MODEL_TOKENS
    assert usage.records[0]["quantity"] == 17
    assert usage.records[0]["idempotency_key"] == "trace-model-1"


@pytest.mark.asyncio
async def test_ocr_upload_and_notification_adapters_record_usage() -> None:
    """验证OCR上传及通知记录用量对应的测试场景。"""
    usage = RecordingUsage()
    ocr = ExpenseOcrService(
        FakeOcr(),
        MemoryExpenseExtractionRepository(),
        invoices=None,  # type: ignore[arg-type]
        usage=usage,
    )
    extraction = await ocr.extract("tenant-meter", b"invoice", "image/png")
    assert extraction.amount_cents == 1234
    assert usage.records[-1]["metric"] == UsageMetric.OCR_PAGES
    assert usage.records[-1]["quantity"] == 3

    uploads = ChunkedUploadService(
        MemoryUploadSessionRepository(),
        MemoryObjectStore(),
        usage=usage,
    )
    session = await uploads.begin(
        tenant_id="tenant-meter",
        owner_module="expense",
        filename="a.txt",
        content_type="text/plain",
        size_bytes=4,
        chunk_size=4,
    )
    await uploads.put_part("tenant-meter", session.upload_id, 1, b"data")
    await uploads.complete("tenant-meter", session.upload_id)
    assert usage.records[-1]["metric"] == UsageMetric.STORAGE_BYTES
    assert usage.records[-1]["quantity"] == 4

    repository = MemoryTicketRepository()
    ticket = Ticket(
        ticket_id="ticket-meter",
        tenant_id="tenant-meter",
        source="feishu",
        subject="SLA",
        status=TicketStatus.WAITING_REVIEW,
        priority=PriorityLevel.P3,
        idempotency_key="ticket-meter",
        metadata={"notification_target": "chat-meter"},
    )
    await repository.save(ticket)
    notification = SupportNotificationService(
        MemoryNotificationGateway(),
        repository,
        usage=usage,
    )
    await notification.handle_sla_event(
        EventEnvelope(
            event_id="sla-meter-1",
            event_type="support.ticket.sla_breached.v1",
            tenant_id="tenant-meter",
            task_id=ticket.ticket_id,
            trace_id="trace-sla",
            producer="test",
            payload={"ticket_id": ticket.ticket_id, "priority": "p3"},
        )
    )
    assert usage.records[-1]["metric"] == UsageMetric.NOTIFICATION_COUNT
    assert usage.records[-1]["quantity"] == 1


@pytest.mark.asyncio
async def test_temporal_client_records_workflow_execution() -> None:
    """验证Temporal客户端记录工作流执行对应的测试场景。"""

    class FakeTemporalClient:
        """用于测试的模拟Temporal。"""

        async def start_workflow(self, *args, **kwargs):
            """启动工作流。

            Args:
                args: 位置参数。
                kwargs: 关键字参数。

            Returns:
                处理结果。
            """
            return None

    async def factory(*args, **kwargs):
        """处理工厂。

        Args:
            args: 位置参数。
            kwargs: 关键字参数。

        Returns:
            处理结果。
        """
        return FakeTemporalClient()

    usage = RecordingUsage()
    client = TemporalWorkflowClient("localhost:7233", "default", client_factory=factory)
    client.set_usage_meter(usage)
    workflow_id = await client.start_workflow(
        object(),
        {"tenant_id": "tenant-meter"},
        workflow_id="workflow-meter-1",
    )
    assert workflow_id == "workflow-meter-1"
    assert usage.records[-1]["metric"] == UsageMetric.WORKFLOW_EXECUTIONS
    assert usage.records[-1]["idempotency_key"] == "workflow:workflow-meter-1"


def test_container_model_gateway_is_wired_to_usage_control_plane() -> None:
    """验证容器模型网关是否到用量对应的测试场景。"""
    app = create_platform_app(load_plugins=False)
    client = TestClient(app)
    provisioned = client.post(
        "/v1/admin/tenants",
        json={
            "tenant_id": "tenant-auto-meter",
            "name": "Auto Meter",
            "plan_name": "starter",
            "actor_id": "ops-admin",
        },
    )
    assert provisioned.status_code == 200
    import asyncio

    asyncio.run(
        app.state.container.model_gateway.complete(
            ModelRequest(
                system_prompt="s",
                user_prompt="hello world",
                metadata={"tenant_id": "tenant-auto-meter", "trace_id": "trace-container-1"},
            )
        )
    )
    summary = client.get("/v1/admin/tenants/tenant-auto-meter/usage")
    assert summary.status_code == 200
    assert summary.json()["metrics"]["model_tokens"]["used"] > 0


@pytest.mark.asyncio
async def test_best_effort_adapter_does_not_break_unknown_tenant() -> None:
    """验证适配器会不未知租户对应的测试场景。"""

    class MissingTenantService:
        """缺失租户应用服务，编排领域用例及其副作用。"""

        async def record(self, **kwargs):
            """记录缺失租户。

            Args:
                kwargs: 关键字参数。

            Raises:
                ValueError: 输入值或业务状态不合法时抛出。
            """
            raise ValueError("tenant not found")

    adapter = UsageMeteringAdapter(MissingTenantService())  # type: ignore[arg-type]
    await adapter.record(
        tenant_id="unknown",
        metric=UsageMetric.OCR_PAGES,
        quantity=1,
        source="test",
        idempotency_key="x",
    )
