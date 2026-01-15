"""AgentForge 平台领域模型层：reporting。

本模块定义 reporting 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：ReportType、ReportFormat、OperationsReport、ScheduledReport、ReportRun。
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReportType(str, Enum):
    """ReportType。

    ReportType 是状态或类型枚举，用于约束系统内部取值，避免使用散落的字符串常量。

    主要成员：
    - COST: 'cost'。
    - AUDIT: 'audit'。
    - QUALITY: 'quality'。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    COST = "cost"
    AUDIT = "audit"
    QUALITY = "quality"


class ReportFormat(str, Enum):
    """ReportFormat。

    ReportFormat 是状态或类型枚举，用于约束系统内部取值，避免使用散落的字符串常量。

    主要成员：
    - JSON: 'json'。
    - CSV: 'csv'。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    JSON = "json"
    CSV = "csv"


class OperationsReport(BaseModel):
    """OperationsReport。

    OperationsReport 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - report_id: str。
    - tenant_id: str。
    - report_type: ReportType。
    - format: ReportFormat。
    - rows: list[dict[str, Any]]。
    - summary: dict[str, Any]。
    - generated_at: datetime。
    - scheduled_report_id: str | None。
    - 方法 to_json()。
    - 方法 to_csv()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
        """执行 to_json 对应的逻辑，并返回处理结果。

        Returns:
            str，函数执行后的结果。
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
        """执行 to_csv 对应的逻辑，并返回处理结果。

        Returns:
            str，函数执行后的结果。
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
    """执行 _json_default 对应的逻辑，并返回处理结果。

    Args:
        value: Any，调用方传入的 value 参数。

    Returns:
        Any，函数执行后的结果。
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _csv_val(value: Any) -> Any:
    """执行 _csv_val 对应的逻辑，并返回处理结果。

    Args:
        value: Any，调用方传入的 value 参数。

    Returns:
        Any，函数执行后的结果。
    """
    if isinstance(value, (datetime, Enum)):
        return _json_default(value)
    return value


class ScheduledReport(BaseModel):
    """ScheduledReport。

    ScheduledReport 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - report_id: str。
    - tenant_id: str。
    - report_type: ReportType。
    - cadence: str。
    - enabled: bool。
    - retention_days: int | None。
    - created_at: datetime。
    - last_run_at: datetime | None。
    - next_run_at: datetime。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    report_id: str
    tenant_id: str
    report_type: ReportType
    cadence: str = "daily"  # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
    enabled: bool = True
    retention_days: int | None = None  # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_run_at: datetime | None = None
    next_run_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReportRun(BaseModel):
    """ReportRun。

    ReportRun 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - run_id: str。
    - tenant_id: str。
    - report_type: ReportType。
    - format: ReportFormat。
    - rows: list[dict[str, Any]]。
    - summary: dict[str, Any]。
    - generated_at: datetime。
    - scheduled_report_id: str | None。
    - archived: bool。
    - 方法 from_operations()。
    - 方法 to_json()。
    - 方法 to_csv()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
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
        """执行 from_operations 对应的逻辑，并返回处理结果。

        Args:
            report: OperationsReport，调用方传入的 report 参数。
            run_id: str | None，调用方传入的 run_id 参数。

        Returns:
            'ReportRun'，函数执行后的结果。
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
        """执行 to_json 对应的逻辑，并返回处理结果。

        Returns:
            str，函数执行后的结果。
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
        """执行 to_csv 对应的逻辑，并返回处理结果。

        Returns:
            str，函数执行后的结果。
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
    """执行 _encode_run_cursor 对应的逻辑，并返回处理结果。

    Args:
        generated_at: Any，调用方传入的 generated_at 参数。
        run_id: Any，调用方传入的 run_id 参数。

    Returns:
        None，函数执行后的结果。
    """
    raw = generated_at.isoformat() + "|" + run_id
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_run_cursor(cursor):
    """执行 _decode_run_cursor 对应的逻辑，并返回处理结果。

    Args:
        cursor: Any，调用方传入的 cursor 参数。

    Returns:
        None，函数执行后的结果。
    """
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        ts, run_id = raw.split("|", 1)
        return datetime.fromisoformat(ts), run_id
    except (ValueError, TypeError):
        return None
