"""AgentForge 平台领域模型层：model。

本模块定义 model 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：ModelRequest、ModelResponse、DraftResult、ModelProfile。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModelRequest(BaseModel):
    """ModelRequest。

    ModelRequest 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - system_prompt: str。
    - user_prompt: str。
    - model: str。
    - temperature: float。
    - metadata: dict[str, Any]。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    system_prompt: str
    user_prompt: str
    model: str = "default"
    temperature: float = 0.2
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelResponse(BaseModel):
    """ModelResponse。

    ModelResponse 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - content: str。
    - model: str。
    - provider: str。
    - input_tokens: int。
    - output_tokens: int。
    - cost_amount: float。
    - latency_ms: float。
    - citations: list[str]。
    - metadata: dict[str, Any]。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
    """DraftResult。

    DraftResult 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - reply_text: str。
    - citations: list[str]。
    - confidence: float。
    - requires_approval: bool。
    - model_name: str。
    - provider: str。
    - input_tokens: int。
    - output_tokens: int。
    - cost_amount: float。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
    """ModelProfile。

    ModelProfile 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - name: str。
    - provider: str。
    - model_id: str。
    - capability_score: float。
    - cost_per_1k_tokens: float。
    - avg_latency_ms: float。
    - task_types: list[str]。
    - is_available: bool。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
