"""提供架构升级适配。"""

from __future__ import annotations

from typing import Any


def set_genai_attributes(span: Any, *, provider: str, model: str, tenant_id: str = "", prompt_version: str = "", operation: str = "chat") -> None:
    """提供架构升级适配。

    Args:
        span: 输入参数。
        provider: 输入参数。
        model: 输入参数。
        tenant_id: 输入参数。
        prompt_version: 输入参数。
        operation: 输入参数。
    """
    if span is None or not hasattr(span, "set_attribute"):
        return
    span.set_attribute("gen_ai.system", provider)
    span.set_attribute("gen_ai.operation.name", operation)
    span.set_attribute("gen_ai.request.model", model)
    if tenant_id:
        span.set_attribute("agentforge.tenant_id", tenant_id)
    if prompt_version:
        span.set_attribute("agentforge.prompt.version", prompt_version)
