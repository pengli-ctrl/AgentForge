from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_prompt: str
    user_prompt: str
    model: str = "default"
    temperature: float = 0.2
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelResponse(BaseModel):
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
    model_config = ConfigDict(extra="forbid")

    name: str
    provider: str
    model_id: str
    capability_score: float
    cost_per_1k_tokens: float
    avg_latency_ms: float
    task_types: list[str] = Field(default_factory=list)
    is_available: bool = True
