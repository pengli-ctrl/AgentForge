from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from agentforge.platform.domain.model import ModelRequest, ModelResponse


class LiteLLMModelGateway:
    def __init__(
        self,
        completion_fn: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        self._completion_fn = completion_fn

    async def complete(self, request: ModelRequest) -> ModelResponse:
        completion_fn = self._completion_fn
        if completion_fn is None:
            import litellm

            completion_fn = litellm.acompletion
        response = await completion_fn(
            model=request.model,
            messages=[
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            temperature=request.temperature,
        )
        content = self._extract_content(response)
        usage = self._extract_usage(response)
        hidden_params = getattr(response, "_hidden_params", {}) or {}
        return ModelResponse(
            content=content,
            model=request.model,
            provider=hidden_params.get("custom_llm_provider", "litellm"),
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
            cost_amount=float(hidden_params.get("response_cost", 0.0) or 0.0),
            citations=list(request.metadata.get("allowed_citations", [])),
        )

    @staticmethod
    def _extract_content(response: Any) -> str:
        choices = response.get("choices", []) if isinstance(response, dict) else response.choices
        if not choices:
            return ""
        message = (
            choices[0].get("message", {}) if isinstance(choices[0], dict) else choices[0].message
        )
        return message.get("content", "") if isinstance(message, dict) else (message.content or "")

    @staticmethod
    def _extract_usage(response: Any) -> dict[str, Any]:
        usage = (
            response.get("usage", {})
            if isinstance(response, dict)
            else getattr(response, "usage", {})
        )
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        return usage or {}
