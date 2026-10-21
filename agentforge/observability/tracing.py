"""追踪模块。"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SpanType(Enum):
    """链路片段枚举。"""

    CACHE = "cache"  # 缓存链路段。
    ROUTE = "route"
    INFERENCE = "inference"
    AGENT = "agent"
    LOOP = "loop"


class SpanStatus(Enum):
    """链路片段状态枚举。"""

    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    DEGRADED = "degraded"
    PARTIAL = "partial"


@dataclass
class Span:
    """链路片段相关组件。

    Attributes:
        span_id: 链路片段ID。
        parent_span_id: 链路片段ID。
        span_type: 链路片段。
        start_time: 开始。
        end_time: 结束。
        status: 当前状态。
        attributes: 字段值。
        name: 名称。
    """

    span_id: str
    parent_span_id: Optional[str]
    span_type: SpanType
    start_time: float
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.OK
    attributes: dict = field(default_factory=dict)
    name: str = ""

    @property
    def duration_ms(self) -> float:
        """返回持续时间。

        Returns:
            数值结果。
        """
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000

    def set_attribute(self, key: str, value) -> None:
        """设置属性。

        Args:
            key: 缓存或配置键。
            value: 待处理值。
        """
        self.attributes[key] = value

    def to_dict(self) -> dict:
        """处理到字典。

        Returns:
            结构化结果字典。
        """
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
    """链路领域组件。

    Attributes:
        trace_id: 链路ID。
        correlation_id: 用于关联同一业务链路的关联 ID。
        root_span: 根链路片段。
        spans: 字段值。
        total_cost: 总计成本。
        total_latency_ms: 总计。
        start_time: 开始。
        end_time: 结束。
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
        """保存链路段。

        Args:
            span: 链路片段对象。
        """
        self.spans.append(span)

    def compute_totals(self) -> None:
        """计算汇总。"""
        self.total_cost = sum(
            s.attributes.get("cost", 0.0) for s in self.spans if s.span_type == SpanType.INFERENCE
        )
        if self.end_time is not None:
            self.total_latency_ms = (self.end_time - self.start_time) * 1000

    def to_dict(self) -> dict:
        """处理到字典。

        Returns:
            结构化结果字典。
        """
        return {
            "trace_id": self.trace_id,
            "correlation_id": self.correlation_id,
            "total_cost": round(self.total_cost, 6),
            "total_latency_ms": round(self.total_latency_ms, 2),
            "span_count": len(self.spans),
            "spans": [s.to_dict() for s in self.spans],
        }


class Tracer:
    """追踪器相关组件。"""

    def __init__(self, max_traces: int = 10000):
        """初始化 Tracer。

        Args:
            max_traces: 最大链路。
        """
        self._traces: dict[str, Trace] = {}
        self._max_traces = max_traces
        self._lock = asyncio.Lock()

    async def start_trace(self, correlation_id: str) -> Trace:
        """执行开始链路。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。

        Returns:
            链路结果。
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
        """启动链路片段。

        Args:
            trace: 链路。
            span_type: 链路片段类型。
            parent_span: 链路片段。
            name: 资源或对象名称。

        Returns:
            链路片段结果。
        """
        parent_id = (
            parent_span.span_id
            if parent_span
            else (trace.root_span.span_id if trace.root_span else None)
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
        """结束链路片段。

        Args:
            span: 链路片段对象。
            status: 目标状态。
            attributes: 输入参数。
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
        """执行结束链路。

        Args:
            trace: 链路。
            status: 目标状态。
        """
        trace.end_time = time.monotonic()
        if trace.root_span:
            trace.root_span.end_time = trace.end_time
            trace.root_span.status = status
        trace.compute_totals()

    async def get_trace(self, trace_id: str) -> Optional[Trace]:
        """读取链路。

        Args:
            trace_id: 链路追踪 ID。

        Returns:
            处理结果对象。
        """
        return self._traces.get(trace_id)

    async def get_span_children(self, trace: Trace, parent_span: Span) -> list[Span]:
        """获取链路片段。

        Args:
            trace: 链路。
            parent_span: 链路片段。

        Returns:
            结果列表。
        """
        return [s for s in trace.spans if s.parent_span_id == parent_span.span_id]

    async def get_spans_by_type(self, trace: Trace, span_type: SpanType) -> list[Span]:
        """获取由。

        Args:
            trace: 链路。
            span_type: 链路片段类型。

        Returns:
            结果列表。
        """
        return [s for s in trace.spans if s.span_type == span_type]
