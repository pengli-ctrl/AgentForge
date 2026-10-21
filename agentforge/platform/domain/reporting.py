"""报告模块。"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReportType(str, Enum):
    """报告枚举。"""

    COST = "cost"
    AUDIT = "audit"
    QUALITY = "quality"


class ReportFormat(str, Enum):
    """报告格式化枚举。"""

    JSON = "json"
    CSV = "csv"


class OperationsReport(BaseModel):
    """操作报告相关组件。

    Attributes:
        report_id: 报告ID。
        tenant_id: 租户 ID，用于数据隔离。
        report_type: 报告。
        format: 格式化。
        rows: 字段值。
        summary: 摘要。
        generated_at: 于。
        scheduled_report_id: 报告ID。
    """

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
        """转换JSON。

        Returns:
            字符串结果。
        """
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
        """处理到CSV。

        Returns:
            字符串结果。
        """
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
    """处理JSON默认。

    Args:
        value: 待处理值。

    Returns:
        处理结果对象。
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _csv_val(value: Any) -> Any:
    """处理CSV。

    Args:
        value: 待处理值。

    Returns:
        处理结果对象。
    """
    if isinstance(value, (datetime, Enum)):
        return _json_default(value)
    return value


class ScheduledReport(BaseModel):
    """报告相关组件。

    Attributes:
        report_id: 报告ID。
        tenant_id: 租户 ID，用于数据隔离。
        report_type: 报告。
        cadence: 周期。
        enabled: 是否启用。
        retention_days: 保留。
        created_at: 创建时间。
        last_run_at: 运行于。
        next_run_at: 下一个运行于。
    """

    model_config = ConfigDict(extra="forbid")

    report_id: str
    tenant_id: str
    report_type: ReportType
    cadence: str = "daily"
    enabled: bool = True
    retention_days: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_run_at: datetime | None = None
    next_run_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReportRun(BaseModel):
    """报告运行相关组件。

    Attributes:
        run_id: 运行ID。
        tenant_id: 租户 ID，用于数据隔离。
        report_type: 报告。
        format: 格式化。
        rows: 字段值。
        summary: 摘要。
        generated_at: 于。
        scheduled_report_id: 报告ID。
        archived: 已归档。
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
        """从操作构造当前对象。

        Args:
            report: 报告。
            run_id: 运行记录 ID。

        Returns:
            处理结果对象。
        """
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
        """转换JSON。

        Returns:
            字符串结果。
        """
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
        """处理到CSV。

        Returns:
            字符串结果。
        """
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
    """编码运行游标。

    Args:
        generated_at: 生成时间。
        run_id: 运行记录 ID。

    Returns:
        处理结果。
    """
    raw = generated_at.isoformat() + "|" + run_id
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_run_cursor(cursor):
    """解码运行游标。

    Args:
        cursor: 分页游标。

    Returns:
        处理结果。
    """
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        ts, run_id = raw.split("|", 1)
        return datetime.fromisoformat(ts), run_id
    except (ValueError, TypeError):
        return None
