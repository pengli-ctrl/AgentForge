"""网关模块。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from agentforge.platform.domain.model import ModelRequest, ModelResponse
from agentforge.platform.observability.trace_recorder import TraceRecord, TraceRecorder


class LiteLLMModelGateway:
    """基于 LiteLLM 的统一模型网关。"""

    def __init__(
        self,
        completion_fn: Callable[..., Awaitable] | None = None,
        recorder: TraceRecorder | None = None,
    ) -> None:
        """初始化 LiteLLMModelGateway。

        Args:
            completion_fn: 完成函数。
            recorder: 记录器。
        """
        self._completion_fn = completion_fn
        self._recorder = recorder

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """完成任务。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            模型响应结果。

        Raises:
            Exception: 操作无法完成时抛出。
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
        """提取内容。

        Args:
            response: 响应。

        Returns:
            字符串结果。
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
        """提取用量。

        Args:
            response: 响应。

        Returns:
            结构化结果字典。
        """
        usage = (
            response.get("usage", {})
            if isinstance(response, dict)
            else getattr(response, "usage", {})
        )
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        return usage or {}
