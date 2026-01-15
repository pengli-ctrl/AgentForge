"""AgentForge 平台可观测性层：tracing。

本模块负责 tracing 相关的平台能力，是 平台可观测性层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：configure_tracing、start_span。
"""

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
    """执行 configure_tracing 对应的逻辑，并返回处理结果。

    Args:
        service_name: str，调用方传入的 service_name 参数。
        endpoint: str | None，调用方传入的 endpoint 参数。
        exporter: SpanExporter | None，调用方传入的 exporter 参数。

    Returns:
        TracerProvider，函数执行后的结果。
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
    """执行 start_span 对应的逻辑，并返回处理结果。

    Args:
        name: str，调用方传入的 name 参数。
        attributes: dict[str, Any] | None，调用方传入的 attributes 参数。

    Returns:
        None，函数执行后的结果。
    """
    tracer = _tracer or trace.get_tracer("agentforge-platform")
    return tracer.start_as_current_span(name, attributes=attributes or {})
