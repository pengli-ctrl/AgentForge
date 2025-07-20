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
    tracer = _tracer or trace.get_tracer("agentforge-platform")
    return tracer.start_as_current_span(name, attributes=attributes or {})
