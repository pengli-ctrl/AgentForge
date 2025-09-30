from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TenantQuota(BaseModel):
    """Per-tenant resource quota for the model gateway and console.

    ``monthly_limit`` caps spend per calendar month; ``warning_threshold`` (0..1)
    is the fraction at which a warning is raised and ``hard_limit``
    (0..1, >= warning) is the fraction at which spend is blocked. A tenant with
    ``enabled=False`` is exempt from quota enforcement.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    monthly_limit: float = 0.0
    warning_threshold: float = 0.8
    hard_limit: float = 1.0
    enabled: bool = True
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def usage_status(self, used: float) -> dict[str, Any]:
        if not self.enabled or self.monthly_limit <= 0:
            return {"status": "active", "used": used, "limit": self.monthly_limit}
        ratio = used / self.monthly_limit
        if ratio >= self.hard_limit:
            status = "blocked"
        elif ratio >= self.warning_threshold:
            status = "warning"
        else:
            status = "active"
        return {
            "status": status,
            "used": used,
            "limit": self.monthly_limit,
            "ratio": round(ratio, 4),
        }
