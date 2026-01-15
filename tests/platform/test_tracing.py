"""AgentForge 平台测试层：test_tracing。

本测试模块验证 test_tracing 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：test_tracing_exports_span_attributes。
"""

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agentforge.platform.observability.tracing import configure_tracing, start_span


def test_tracing_exports_span_attributes() -> None:
    """验证 tracing_exports_span_attributes 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    exporter = InMemorySpanExporter()
    provider = configure_tracing(exporter=exporter)
    with start_span("test.span", {"tenant_id": "tenant-1"}):
        pass
    provider.force_flush()
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "test.span"
    assert spans[0].attributes["tenant_id"] == "tenant-1"
