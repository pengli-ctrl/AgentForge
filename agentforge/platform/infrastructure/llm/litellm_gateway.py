"""AgentForge 平台基础设施层：litellm_gateway。

本模块封装 litellm_gateway 对应外部系统或基础设施协议，提供稳定、可替换的适配接口。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：LiteLLMModelGateway。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from agentforge.platform.domain.model import ModelRequest, ModelResponse
from agentforge.platform.observability.trace_recorder import TraceRecord, TraceRecorder


class LiteLLMModelGateway:
    """LiteLLMModelGateway。

    LiteLLMModelGateway 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

    主要成员：
    - 方法 complete()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        completion_fn: Callable[..., Awaitable] | None = None,
        recorder: TraceRecorder | None = None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            completion_fn: Callable[..., Awaitable] | None，调用方传入的 completion_fn 参数。
            recorder: TraceRecorder | None，调用方传入的 recorder 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._completion_fn = completion_fn
        self._recorder = recorder

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """执行 complete 对应的逻辑，并返回处理结果。

        Args:
            request: ModelRequest，调用方传入的 request 参数。

        Returns:
            ModelResponse，函数执行后的结果。
        """
        completion_fn = self._completion_fn
        if completion_fn is None:
            import litellm

            completion_fn = litellm.acompletion
        import time

        _start = time.monotonic()
        try:
            response = await completion_fn(
                model=request.model,
                messages=[
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.user_prompt},
                ],
                temperature=request.temperature,
            )
        except BaseException as exc:  # noqa: BLE001 - record failure, re-raise
            if self._recorder is not None:
                self._recorder.record(
                    TraceRecord(
                        trace_id=request.metadata.get("trace_id", ""),
                        tenant_id=request.metadata.get("tenant_id", ""),
                        model=request.model,
                        provider="litellm",
                        status="error",
                        latency_ms=(time.monotonic() - _start) * 1000,
                        error=str(exc)[:200],
                    )
                )
            raise
        _latency_ms = (time.monotonic() - _start) * 1000
        content = self._extract_content(response)
        usage = self._extract_usage(response)
        hidden_params = getattr(response, "_hidden_params", {}) or {}
        result = ModelResponse(
            content=content,
            model=request.model,
            provider=hidden_params.get("custom_llm_provider", "litellm"),
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
            cost_amount=float(hidden_params.get("response_cost", 0.0) or 0.0),
            latency_ms=_latency_ms,
            citations=list(request.metadata.get("allowed_citations", [])),
        )
        if self._recorder is not None:
            self._recorder.record(
                TraceRecord(
                    trace_id=request.metadata.get("trace_id", ""),
                    tenant_id=request.metadata.get("tenant_id", ""),
                    model=request.model,
                    provider=result.provider,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cost_amount=result.cost_amount,
                    latency_ms=_latency_ms,
                )
            )
        return result

    @staticmethod
    def _extract_content(response) -> str:
        """执行 _extract_content 对应的逻辑，并返回处理结果。

        Args:
            response: Any，调用方传入的 response 参数。

        Returns:
            str，函数执行后的结果。
        """
        choices = response.get("choices", []) if isinstance(response, dict) else response.choices
        if not choices:
            return ""
        message = (
            choices[0].get("message", {}) if isinstance(choices[0], dict) else choices[0].message
        )
        return message.get("content", "") if isinstance(message, dict) else (message.content or "")

    @staticmethod
    def _extract_usage(response) -> dict:
        """执行 _extract_usage 对应的逻辑，并返回处理结果。

        Args:
            response: Any，调用方传入的 response 参数。

        Returns:
            dict，函数执行后的结果。
        """
        usage = (
            response.get("usage", {})
            if isinstance(response, dict)
            else getattr(response, "usage", {})
        )
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        return usage or {}
