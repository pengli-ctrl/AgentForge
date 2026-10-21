"""OCR模块。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OcrField(BaseModel):
    """OCR字段相关组件。

    Attributes:
        name: 名称。
        value: 值。
        confidence: 字段值。
        bounding_box: 字段值。
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    value: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    bounding_box: list[float] = Field(default_factory=list)


class OcrResult(BaseModel):
    """OCR结果领域组件。

    Attributes:
        text: 文本。
        fields: 字段。
        provider: 提供方。
        metadata: 附加元数据。
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    fields: list[OcrField] = Field(default_factory=list)
    provider: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
