"""AgentForge 平台基础设施层：static_gateway。

本模块封装 static_gateway 对应外部系统或基础设施协议，提供稳定、可替换的适配接口。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：StaticModelGateway。
"""

from __future__ import annotations

import time

from agentforge.platform.domain.model import ModelRequest, ModelResponse
from agentforge.platform.observability.trace_recorder import TraceRecord, TraceRecorder


class StaticModelGateway:
    """StaticModelGateway。

    StaticModelGateway 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

    主要成员：
    - 方法 complete()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, recorder: TraceRecorder | None = None) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            recorder: TraceRecorder | None，调用方传入的 recorder 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._recorder = recorder

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """执行 complete 对应的逻辑，并返回处理结果。

        Args:
            request: ModelRequest，调用方传入的 request 参数。

        Returns:
            ModelResponse，函数执行后的结果。
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
