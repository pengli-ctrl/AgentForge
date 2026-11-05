"""写入 GenAI 链路属性。"""

from __future__ import annotations

from typing import Any


def set_genai_attributes(span: Any, *, provider: str, model: str, tenant_id: str = "", prompt_version: str = "", operation: str = "chat") -> None:
    """写入 GenAI 链路属性。

    Args:
        span: 调用该函数所需的输入值。
        provider: 调用该函数所需的输入值。
        model: 调用该函数所需的输入值。
        tenant_id: 调用该函数所需的输入值。
        prompt_version: 调用该函数所需的输入值。
        operation: 调用该函数所需的输入值。
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
