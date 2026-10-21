"""追踪模块。"""

from __future__ import annotations

from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

_tracer = None


def configure_tracing(
    service_name: str = "agentforge-platform",
    endpoint: str | None = None,
    exporter: SpanExporter | None = None,
) -> TracerProvider:
    """配置追踪。

    Args:
        service_name: 服务名称。
        endpoint: 端点。
        exporter: 输入参数。

    Returns:
        追踪器提供方结果。
    """
    global _tracer
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    if exporter is not None:
        provider.add_span_processor(BatchSpanProcessor(exporter))
    elif endpoint:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name)
    return provider


def start_span(name: str, attributes: dict[str, Any] | None = None):
    """启动链路片段。

    Args:
        name: 资源或对象名称。
        attributes: 输入参数。

    Returns:
        处理结果。
    """
    tracer = _tracer or trace.get_tracer("agentforge-platform")
    return tracer.start_as_current_span(name, attributes=attributes or {})
