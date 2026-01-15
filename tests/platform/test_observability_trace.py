"""AgentForge 平台测试层：test_observability_trace。

本测试模块验证 test_observability_trace 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_trace_llm_call_recorded、test_trace_recorder_fifo_cap、test_trace_recorder_summary_metrics、test_dashboard_traces_endpoint、test_support_processing_propagates_trace_id_to_recorder。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.application.support_ticket_processing_service import (
    SupportTicketProcessingService,
)
from agentforge.platform.domain.model import ModelRequest
from agentforge.platform.infrastructure.llm.static_gateway import StaticModelGateway
from agentforge.platform.observability.trace_recorder import TraceRecord, TraceRecorder
from agentforge.platform.runtime import build_memory_container


@pytest.mark.asyncio
async def test_trace_llm_call_recorded() -> None:
    """验证 trace_llm_call_recorded 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    recorder = TraceRecorder()
    gateway = StaticModelGateway(recorder=recorder)

    await gateway.complete(
        ModelRequest(
            system_prompt="sys",
            user_prompt="resolve billing issue",
            metadata={"trace_id": "trace-xyz", "tenant_id": "tenant-a"},
        )
    )
    records = await recorder.list_recent(tenant_id="tenant-a")
    assert len(records) == 1
    rec = records[0]
    assert rec.trace_id == "trace-xyz"
    assert rec.tenant_id == "tenant-a"
    assert rec.model == "static-local"
    assert rec.provider == "local"
    assert rec.input_tokens > 0


@pytest.mark.asyncio
async def test_trace_recorder_fifo_cap() -> None:
    """验证 trace_recorder_fifo_cap 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    recorder = TraceRecorder(max_records=3)
    for i in range(5):
        recorder.record(
            TraceRecord(
                trace_id=f"t{i}",
                tenant_id="tenant-a",
                model="m",
                provider="p",
                status="ok",
            )
        )
    recent = await recorder.list_recent()
    assert len(recent) == 3
    # 最旧的 t0/t1 被淘汰，最新的是 t4
    assert {r.trace_id for r in recent} == {"t2", "t3", "t4"}
    assert recent[0].trace_id == "t4"


@pytest.mark.asyncio
async def test_trace_recorder_summary_metrics() -> None:
    """验证 trace_recorder_summary_metrics 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    recorder = TraceRecorder()
    recorder.record(
        TraceRecord(
            trace_id="a",
            tenant_id="tenant-a",
            model="m1",
            provider="p",
            input_tokens=10,
            output_tokens=5,
            cost_amount=0.01,
            latency_ms=100.0,
            status="ok",
        )
    )
    recorder.record(
        TraceRecord(
            trace_id="b",
            tenant_id="tenant-a",
            model="m2",
            provider="p",
            cost_amount=0.02,
            latency_ms=300.0,
            status="error",
            error="boom",
        )
    )
    s = await recorder.summary("tenant-a")
    assert s["count"] == 2
    assert s["total_cost"] == pytest.approx(0.03)
    assert s["total_latency_ms"] == pytest.approx(400.0)
    assert s["avg_latency_ms"] == pytest.approx(200.0)
    assert s["ok_rate"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_dashboard_traces_endpoint() -> None:
    """验证 dashboard_traces_endpoint 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    recorder = TraceRecorder()
    recorder.record(
        TraceRecord(
            trace_id="trace-1",
            tenant_id="tenant-a",
            model="static-local",
            provider="local",
            input_tokens=32,
            output_tokens=8,
            cost_amount=0.0,
            latency_ms=5.0,
            status="ok",
        )
    )

    container = build_memory_container()
    container.trace_recorder = recorder
    container.dashboard_service.attach_trace_recorder(recorder)

    app = create_platform_app(container)
    client = TestClient(app)
    resp = client.get("/v1/console/traces", params={"tenant_id": "tenant-a"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["records"][0]["trace_id"] == "trace-1"
    assert data["records"][0]["tenant_id"] == "tenant-a"


@pytest.mark.asyncio
async def test_support_processing_propagates_trace_id_to_recorder() -> None:
    """验证 support_processing_propagates_trace_id_to_recorder 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    container = build_memory_container()
    recorder = container.trace_recorder
    assert recorder is not None
    service: SupportTicketProcessingService = container.processing_service

    # seed 一条 tenant-a 的知识文档，让检索命中并真正触达 LLM 调用
    from agentforge.platform.domain.knowledge import KnowledgeChunk, KnowledgeDocument

    await container.knowledge_repository.save_document(
        KnowledgeDocument(
            document_id="doc-obs-1",
            tenant_id="tenant-a",
            title="Billing policy",
            content="Customers may request a refund within 30 days of purchase.",
            source_uri="docs://billing",
            version=1,
        ),
        [
            KnowledgeChunk(
                chunk_id="chunk-obs-1",
                document_id="doc-obs-1",
                tenant_id="tenant-a",
                content="Customers may request a refund within 30 days of purchase.",
                position=0,
            )
        ],
    )

    await service.process_event(
        {
            "tenant_id": "tenant-a",
            "source": "feishu",
            "message_id": "msg-obs-1",
            "text": "billing overcharge",
            "idempotency_key": "key-1",
        }
    )
    s = await recorder.summary("tenant-a")
    assert s["count"] == 1
    rec = s["records"][0]
    assert rec["tenant_id"] == "tenant-a"
    assert rec["model"] == "static-local"
    assert rec["cost_amount"] >= 0
