from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReportType(str, Enum):
    """Operational report kinds available for export / scheduling."""

    COST = "cost"
    AUDIT = "audit"
    QUALITY = "quality"


class ReportFormat(str, Enum):
    """Supported export serialization formats."""

    JSON = "json"
    CSV = "csv"


class OperationsReport(BaseModel):
    """A materialized operational report (rows + summary + serialized content)."""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    tenant_id: str
    report_type: ReportType
    format: ReportFormat = ReportFormat.JSON
    rows: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scheduled_report_id: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "report_type": self.report_type.value,
                "tenant_id": self.tenant_id,
                "generated_at": self.generated_at.isoformat(),
                "summary": self.summary,
                "rows": self.rows,
            },
            ensure_ascii=False,
            default=_json_default,
        )

    def to_csv(self) -> str:
        import csv
        import io

        if not self.rows:
            return ""
        header = list(self.rows[0].keys())
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for row in self.rows:
            writer.writerow({k: _csv_val(v) for k, v in row.items()})
        return buf.getvalue()


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _csv_val(value: Any) -> Any:
    if isinstance(value, (datetime, Enum)):
        return _json_default(value)
    return value


class ScheduledReport(BaseModel):
    """A recurring operational report schedule (cadence + next_run)."""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    tenant_id: str
    report_type: ReportType
    cadence: str = "daily"  # daily | weekly | monthly (simple label)
    enabled: bool = True
    retention_days: int | None = None  # None = no auto-prune on run
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_run_at: datetime | None = None
    next_run_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReportRun(BaseModel):
    """A persisted operational report run (materialized rows + summary).

    Immutable snapshot of a generated report: stores rows, summary and
    provenance (source schedule when produced by run_due) so historical
    exports can be re-served as JSON/CSV without re-aggregation.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    tenant_id: str
    report_type: ReportType
    format: ReportFormat = ReportFormat.JSON
    rows: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scheduled_report_id: str | None = None
    archived: bool = False

    @classmethod
    def from_operations(
        cls,
        report: OperationsReport,
        run_id: str | None = None,
    ) -> "ReportRun":
        return cls(
            run_id=run_id or report.report_id,
            tenant_id=report.tenant_id,
            report_type=report.report_type,
            format=report.format,
            rows=report.rows,
            summary=report.summary,
            generated_at=report.generated_at,
            scheduled_report_id=report.scheduled_report_id,
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "report_type": self.report_type.value,
                "tenant_id": self.tenant_id,
                "generated_at": self.generated_at.isoformat(),
                "summary": self.summary,
                "rows": self.rows,
                "scheduled_report_id": self.scheduled_report_id,
            },
            ensure_ascii=False,
            default=_json_default,
        )

    def to_csv(self) -> str:
        import csv
        import io

        if not self.rows:
            return ""
        header = list(self.rows[0].keys())
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for row in self.rows:
            writer.writerow({k: _csv_val(v) for k, v in row.items()})
        return buf.getvalue()


def _encode_run_cursor(generated_at, run_id):
    """URL-safe keyset cursor for a report run (generated_at, run_id)."""
    raw = generated_at.isoformat() + "|" + run_id
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_run_cursor(cursor):
    """Decode a keyset cursor into (generated_at, run_id); None if invalid."""
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        ts, run_id = raw.split("|", 1)
        return datetime.fromisoformat(ts), run_id
    except (ValueError, TypeError):
        return None
