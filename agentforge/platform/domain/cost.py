from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class CostRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    task_id: str
    model_name: str
    provider: str
    input_tokens: int
    output_tokens: int
    amount: float
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
