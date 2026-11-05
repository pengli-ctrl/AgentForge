"""OpenTelemetry GenAI semantic attribute helpers."""

from __future__ import annotations

from typing import Any


def set_genai_attributes(span: Any, *, provider: str, model: str, tenant_id: str = "", prompt_version: str = "", operation: str = "chat") -> None:
    if span is None or not hasattr(span, "set_attribute"):
        return
    span.set_attribute("gen_ai.system", provider)
    span.set_attribute("gen_ai.operation.name", operation)
    span.set_attribute("gen_ai.request.model", model)
    if tenant_id:
        span.set_attribute("agentforge.tenant_id", tenant_id)
    if prompt_version:
        span.set_attribute("agentforge.prompt.version", prompt_version)
