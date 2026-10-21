"""模型模块。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModelRequest(BaseModel):
    """模型请求领域组件。

    Attributes:
        system_prompt: 系统提示词。
        user_prompt: 用户提示词。
        model: 模型。
        temperature: 模型采样温度。
        metadata: 附加元数据。
    """

    model_config = ConfigDict(extra="forbid")

    system_prompt: str
    user_prompt: str
    model: str = "default"
    temperature: float = 0.2
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelResponse(BaseModel):
    """模型响应领域组件。

    Attributes:
        content: 写入内容。
        model: 模型。
        provider: 提供方。
        input_tokens: 输入。
        output_tokens: 输出。
        cost_amount: 成本金额。
        latency_ms: 延迟，单位为毫秒。
        citations: 引用。
        metadata: 附加元数据。
    """

    model_config = ConfigDict(extra="forbid")

    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_amount: float = 0.0
    latency_ms: float = 0.0
    citations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DraftResult(BaseModel):
    """草稿结果相关组件。

    Attributes:
        reply_text: 回复文本。
        citations: 引用。
        confidence: 字段值。
        requires_approval: 要求审批。
        model_name: 模型名称。
        provider: 提供方。
        input_tokens: 输入。
        output_tokens: 输出。
        cost_amount: 成本金额。
    """

    model_config = ConfigDict(extra="forbid")

    reply_text: str
    citations: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    requires_approval: bool = True
    model_name: str = ""
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_amount: float = 0.0


class ModelProfile(BaseModel):
    """模型配置相关组件。

    Attributes:
        name: 名称。
        provider: 提供方。
        model_id: 模型ID。
        capability_score: 能力评分。
        cost_per_1k_tokens: 成本。
        avg_latency_ms: 延迟毫秒。
        task_types: 任务。
        is_available: 是否可用。
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    provider: str
    model_id: str
    capability_score: float
    cost_per_1k_tokens: float
    avg_latency_ms: float
    task_types: list[str] = Field(default_factory=list)
    is_available: bool = True
