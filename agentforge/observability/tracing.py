"""AgentForge 可观测性层：tracing。

本模块负责 tracing 相关能力，是 可观测性层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：SpanType、SpanStatus、Span、Trace、Tracer。
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SpanType(Enum):
    """SpanType。

    SpanType 是状态或类型枚举，用于约束系统内部取值，避免散落的字符串常量。

    主要成员：
    - CACHE: 'cache'。
    - ROUTE: 'route'。
    - INFERENCE: 'inference'。
    - AGENT: 'agent'。
    - LOOP: 'loop'。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    CACHE = "cache"  # 缓存处理。
    ROUTE = "route"  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    INFERENCE = "inference"  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    AGENT = "agent"  # Agent 注册与查询。
    LOOP = "loop"  # 说明：该步骤用于实现上述逻辑并保证行为稳定。


class SpanStatus(Enum):
    """SpanStatus。

    SpanStatus 是状态或类型枚举，用于约束系统内部取值，避免散落的字符串常量。

    主要成员：
    - OK: 'ok'。
    - ERROR: 'error'。
    - TIMEOUT: 'timeout'。
    - DEGRADED: 'degraded'。
    - PARTIAL: 'partial'。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    DEGRADED = "degraded"  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    PARTIAL = "partial"  # 说明：该步骤用于实现上述逻辑并保证行为稳定。


@dataclass
class Span:
    """Span。

    Span 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - span_id: str。
    - parent_span_id: Optional[str]。
    - span_type: SpanType。
    - start_time: float。
    - end_time: Optional[float]。
    - status: SpanStatus。
    - attributes: dict。
    - name: str。
    - 方法 duration_ms()。
    - 方法 set_attribute()。
    - 方法 to_dict()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    span_id: str
    parent_span_id: Optional[str]
    span_type: SpanType
    start_time: float  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.OK
    attributes: dict = field(default_factory=dict)
    name: str = ""

    @property
    def duration_ms(self) -> float:
        """执行 duration_ms 对应的逻辑，并返回处理结果。

        Returns:
            float，函数执行后的结果。
        """
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time) * 1000

    def set_attribute(self, key: str, value) -> None:
        """执行 set_attribute 对应的逻辑，并返回处理结果。

        Args:
            key: str，调用方传入的 key 参数。
            value: Any，调用方传入的 value 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.attributes[key] = value

    def to_dict(self) -> dict:
        """执行 to_dict 对应的逻辑，并返回处理结果。

        Returns:
            dict，函数执行后的结果。
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
    """Trace。

    Trace 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - trace_id: str。
    - correlation_id: str。
    - root_span: Optional[Span]。
    - spans: list[Span]。
    - total_cost: float。
    - total_latency_ms: float。
    - start_time: float。
    - end_time: Optional[float]。
    - 方法 add_span()。
    - 方法 compute_totals()。
    - 方法 to_dict()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
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
        """执行 add_span 对应的逻辑，并返回处理结果。

        Args:
            span: Span，调用方传入的 span 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.spans.append(span)

    def compute_totals(self) -> None:
        """执行 compute_totals 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
        self.total_cost = sum(
            s.attributes.get("cost", 0.0) for s in self.spans if s.span_type == SpanType.INFERENCE
        )
        if self.end_time is not None:
            self.total_latency_ms = (self.end_time - self.start_time) * 1000

    def to_dict(self) -> dict:
        """执行 to_dict 对应的逻辑，并返回处理结果。

        Returns:
            dict，函数执行后的结果。
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
    """Tracer。

    Tracer 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 start_trace()。
    - 方法 start_span()。
    - 方法 end_span()。
    - 方法 end_trace()。
    - 方法 get_trace()。
    - 方法 get_span_children()。
    - 方法 get_spans_by_type()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(self, max_traces: int = 10000):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            max_traces: int，调用方传入的 max_traces 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._traces: dict[str, Trace] = {}
        self._max_traces = max_traces
        self._lock = asyncio.Lock()

    async def start_trace(self, correlation_id: str) -> Trace:
        """执行 start_trace 对应的逻辑，并返回处理结果。

        Args:
            correlation_id: str，调用方传入的 correlation_id 参数。

        Returns:
            Trace，函数执行后的结果。
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
            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
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
        """执行 start_span 对应的逻辑，并返回处理结果。

        Args:
            trace: Trace，调用方传入的 trace 参数。
            span_type: SpanType，调用方传入的 span_type 参数。
            parent_span: Optional[Span]，调用方传入的 parent_span 参数。
            name: str，调用方传入的 name 参数。

        Returns:
            Span，函数执行后的结果。
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
        """执行 end_span 对应的逻辑，并返回处理结果。

        Args:
            span: Span，调用方传入的 span 参数。
            status: SpanStatus，调用方传入的 status 参数。
            attributes: Optional[dict]，调用方传入的 attributes 参数。

        Returns:
            None，函数执行后的结果。
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
        """执行 end_trace 对应的逻辑，并返回处理结果。

        Args:
            trace: Trace，调用方传入的 trace 参数。
            status: SpanStatus，调用方传入的 status 参数。

        Returns:
            None，函数执行后的结果。
        """
        trace.end_time = time.monotonic()
        if trace.root_span:
            trace.root_span.end_time = trace.end_time
            trace.root_span.status = status
        trace.compute_totals()

    async def get_trace(self, trace_id: str) -> Optional[Trace]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            trace_id: str，调用方传入的 trace_id 参数。

        Returns:
            Optional[Trace]，函数执行后的结果。
        """
        return self._traces.get(trace_id)

    async def get_span_children(self, trace: Trace, parent_span: Span) -> list[Span]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            trace: Trace，调用方传入的 trace 参数。
            parent_span: Span，调用方传入的 parent_span 参数。

        Returns:
            list[Span]，函数执行后的结果。
        """
        return [s for s in trace.spans if s.parent_span_id == parent_span.span_id]

    async def get_spans_by_type(self, trace: Trace, span_type: SpanType) -> list[Span]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            trace: Trace，调用方传入的 trace 参数。
            span_type: SpanType，调用方传入的 span_type 参数。

        Returns:
            list[Span]，函数执行后的结果。
        """
        return [s for s in trace.spans if s.span_type == span_type]
