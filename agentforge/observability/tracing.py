"""
Full-chain Trace/Span tracking — five Span types for unified observability.

Span Types:
    CacheSpan   — semantic cache hit/miss, similarity score, eviction events
    RouteSpan   — model routing decision, scores, cost/latency estimation
    InferenceSpan — single LLM call, token counts, latency, cost
    AgentSpan   — individual Agent execution within a DAG node
    LoopSpan    — LoopBlock iteration tracking, iteration count, exit reason

Design rationale:
    OpenTelemetry-style parent-child span hierarchy enables tracing across
    all three layers (orchestration → runtime → gateway). Each span carries
    attributes dict for flexible metadata without rigid schema.
"""

import uuid
import time
import asyncio
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field


class SpanType(Enum):
    """Five span types covering the full request lifecycle."""
    CACHE = "cache"            # Gateway layer: semantic cache lookup
    ROUTE = "route"            # Gateway layer: model routing decision
    INFERENCE = "inference"    # Gateway layer: actual LLM API call
    AGENT = "agent"            # Runtime layer: Agent execution
    LOOP = "loop"              # Orchestration layer: LoopBlock iteration


class SpanStatus(Enum):
    """Span completion status."""
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    DEGRADED = "degraded"      # Completed with degradation applied
    PARTIAL = "partial"        # Partial success (DAG-level)


@dataclass
class Span:
    """
    Single span in the trace tree.

    Mirrors OpenTelemetry Span semantics but simplified for our use case.
    parent_span_id=None means this is a root span of its trace.
    """
    span_id: str
    parent_span_id: Optional[str]
    span_type: SpanType
    start_time: float                           # time.monotonic() for precision
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.OK
    attributes: dict = field(default_factory=dict)
    name: str = ""

    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds. Returns 0 if span is still open."""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000

    def set_attribute(self, key: str, value) -> None:
        """Set a single attribute. Called during span lifecycle."""
        self.attributes[key] = value

    def to_dict(self) -> dict:
        """Serialize span for logging/export."""
        return {
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "span_type": self.span_type.value,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "attributes": self.attributes,
        }


@dataclass
class Trace:
    """
    Complete trace for a single request (DAG execution).

    A trace is a tree of spans rooted at root_span.
    total_cost and total_latency are computed at trace end by aggregating
    all child spans — this avoids double-counting in nested spans.
    """
    trace_id: str
    correlation_id: str
    root_span: Optional[Span] = None
    spans: list[Span] = field(default_factory=list)
    total_cost: float = 0.0
    total_latency_ms: float = 0.0
    start_time: float = field(default_factory=time.monotonic)
    end_time: Optional[float] = None

    def add_span(self, span: Span) -> None:
        """Register a span in this trace."""
        self.spans.append(span)

    def compute_totals(self) -> None:
        """
        Aggregate cost and latency from leaf INFERENCE spans.
        Only INFERENCE spans carry actual cost (token pricing).
        Latency is computed from the root span duration.
        """
        self.total_cost = sum(
            s.attributes.get("cost", 0.0)
            for s in self.spans
            if s.span_type == SpanType.INFERENCE
        )
        if self.end_time is not None:
            self.total_latency_ms = (self.end_time - self.start_time) * 1000

    def to_dict(self) -> dict:
        """Serialize entire trace tree for export/logging."""
        return {
            "trace_id": self.trace_id,
            "correlation_id": self.correlation_id,
            "total_cost": round(self.total_cost, 6),
            "total_latency_ms": round(self.total_latency_ms, 2),
            "span_count": len(self.spans),
            "spans": [s.to_dict() for s in self.spans],
        }


class Tracer:
    """
    Central tracer managing trace lifecycle and span creation.

    Thread-safety: uses asyncio.Lock for concurrent DAG node executions
    that may start/end spans in parallel.

    Storage: in-memory dict keyed by trace_id. In production, replace
    _traces with an OTLP exporter or async batch writer.
    """

    def __init__(self, max_traces: int = 10000):
        """
        Args:
            max_traces: Max traces kept in memory. Oldest are evicted (FIFO).
                        10000 ≈ ~1GB at typical span density.
        """
        self._traces: dict[str, Trace] = {}
        self._max_traces = max_traces
        self._lock = asyncio.Lock()

    async def start_trace(self, correlation_id: str) -> Trace:
        """
        Begin a new trace for an incoming request.

        Args:
            correlation_id: Business-level request ID (from HTTP header or
                           DAG execution). Used for cross-system correlation.

        Returns:
            Initialized Trace with a root span already created.
        """
        trace_id = f"trace-{uuid.uuid4().hex[:16]}"
        root_span = Span(
            span_id=f"span-{uuid.uuid4().hex[:12]}",
            parent_span_id=None,
            span_type=SpanType.AGENT,
            start_time=time.monotonic(),
            name=f"root:{correlation_id}",
        )

        trace = Trace(
            trace_id=trace_id,
            correlation_id=correlation_id,
            root_span=root_span,
        )
        trace.add_span(root_span)

        async with self._lock:
            # Evict oldest traces if at capacity (FIFO)
            if len(self._traces) >= self._max_traces:
                oldest_key = next(iter(self._traces))
                del self._traces[oldest_key]
            self._traces[trace_id] = trace

        return trace

    async def start_span(
        self,
        trace: Trace,
        span_type: SpanType,
        parent_span: Optional[Span] = None,
        name: str = "",
    ) -> Span:
        """
        Create a child span within an existing trace.

        Args:
            trace: The trace this span belongs to.
            span_type: One of the five span types.
            parent_span: Parent span for hierarchy. None → direct child of root.
            name: Human-readable span name (e.g., "agent:classifier", "llm:qwen3").

        Returns:
            New Span with start_time already set.
        """
        parent_id = parent_span.span_id if parent_span else (
            trace.root_span.span_id if trace.root_span else None
        )

        span = Span(
            span_id=f"span-{uuid.uuid4().hex[:12]}",
            parent_span_id=parent_id,
            span_type=span_type,
            start_time=time.monotonic(),
            name=name or f"{span_type.value}",
        )
        trace.add_span(span)
        return span

    async def end_span(
        self,
        span: Span,
        status: SpanStatus = SpanStatus.OK,
        attributes: Optional[dict] = None,
    ) -> None:
        """
        Complete a span, recording final status and attributes.

        Args:
            span: The span to end.
            status: Completion status (ok/error/timeout/degraded/partial).
            attributes: Final attributes to merge (token counts, cost, etc.).
        """
        span.end_time = time.monotonic()
        span.status = status
        if attributes:
            span.attributes.update(attributes)

    async def end_trace(
        self,
        trace: Trace,
        status: SpanStatus = SpanStatus.OK,
    ) -> None:
        """
        Complete an entire trace.

        Ends the root span and computes aggregate totals.
        This should be called in a finally block to ensure
        traces are always properly closed.
        """
        trace.end_time = time.monotonic()
        if trace.root_span:
            trace.root_span.end_time = trace.end_time
            trace.root_span.status = status
        trace.compute_totals()

    async def get_trace(self, trace_id: str) -> Optional[Trace]:
        """Retrieve a trace by ID. Returns None if not found or evicted."""
        return self._traces.get(trace_id)

    async def get_span_children(
        self, trace: Trace, parent_span: Span
    ) -> list[Span]:
        """Get all direct children of a span within a trace."""
        return [
            s for s in trace.spans
            if s.parent_span_id == parent_span.span_id
        ]

    async def get_spans_by_type(
        self, trace: Trace, span_type: SpanType
    ) -> list[Span]:
        """Filter spans by type. Useful for cost/latency aggregation."""
        return [s for s in trace.spans if s.span_type == span_type]
