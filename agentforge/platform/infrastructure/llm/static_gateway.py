"""静态网关模块。"""

from __future__ import annotations

import time

from agentforge.platform.domain.model import ModelRequest, ModelResponse
from agentforge.platform.observability.trace_recorder import TraceRecord, TraceRecorder


class StaticModelGateway:
    """静态模型网关抽象。"""

    def __init__(self, recorder: TraceRecorder | None = None) -> None:
        """初始化 StaticModelGateway。

        Args:
            recorder: 记录器。
        """
        self._recorder = recorder

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """完成静态模型。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            模型响应结果。
        """
        citations = list(request.metadata.get("allowed_citations", []))
        _start = time.monotonic()
        _content = "Draft response generated from approved knowledge."
        _in = len(request.user_prompt.split())
        _out = 8
        result = ModelResponse(
            content=_content,
            model="static-local",
            provider="local",
            input_tokens=_in,
            output_tokens=_out,
            cost_amount=0.0,
            latency_ms=(time.monotonic() - _start) * 1000,
            citations=citations,
        )
        if self._recorder is not None:
            self._recorder.record(
                TraceRecord(
                    trace_id=request.metadata.get("trace_id", ""),
                    tenant_id=request.metadata.get("tenant_id", ""),
                    model=result.model,
                    provider=result.provider,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cost_amount=result.cost_amount,
                    latency_ms=result.latency_ms,
                )
            )
        return result
