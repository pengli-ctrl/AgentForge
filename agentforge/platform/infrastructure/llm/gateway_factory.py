"""Selection of the model-gateway backend."""

from __future__ import annotations

from agentforge.platform.infrastructure.llm.litellm_gateway import LiteLLMModelGateway
from agentforge.platform.infrastructure.llm.static_gateway import StaticModelGateway
from agentforge.platform.observability.trace_recorder import TraceRecorder
from agentforge.platform.settings import Settings


def build_inner_model_gateway(settings: Settings, recorder: TraceRecorder | None = None, *, default_backend: str = "static"):
    """Return the configured provider adapter while preserving the existing port."""
    backend = settings.ai_gateway_backend
    if backend == "local":
        backend = default_backend
    if backend == "litellm":
        return LiteLLMModelGateway(
            recorder=recorder,
            api_base=settings.litellm_proxy_url,
            api_key=settings.litellm_api_key,
        )
    if backend == "static":
        return StaticModelGateway(recorder=recorder)
    raise ValueError(f"unsupported ai_gateway_backend: {backend}")
