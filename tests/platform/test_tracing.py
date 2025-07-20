from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agentforge.platform.observability.tracing import configure_tracing, start_span


def test_tracing_exports_span_attributes() -> None:
    exporter = InMemorySpanExporter()
    provider = configure_tracing(exporter=exporter)
    with start_span("test.span", {"tenant_id": "tenant-1"}):
        pass
    provider.force_flush()
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "test.span"
    assert spans[0].attributes["tenant_id"] == "tenant-1"
