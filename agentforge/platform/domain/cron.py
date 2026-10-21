"""定时任务模块。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Collection


class CronExpressionError(ValueError):
    """定时任务表达式错误相关组件。"""


@dataclass(frozen=True)
class CronField:
    """定时任务字段相关组件。

    Attributes:
        name: 名称。
        allowed: 允许。
        expr: 字段值。
    """

    name: str
    allowed: Collection[int]
    expr: str

    @classmethod
    def parse(cls, name: str, field: str, low: int, high: int) -> "CronField":
        """解析定时任务字段。

        Args:
            name: 资源或对象名称。
            field: 字段。
            low: 低。
            high: 高。

        Returns:
            处理结果对象。

        Raises:
            CronExpressionError: 操作无法完成时抛出。
        """
        allowed: set[int] = set()
        for part in field.split(","):
            part = part.strip()
            if not part:
                raise CronExpressionError(f"empty {name} field")
            if part == "*":
                allowed.update(range(low, high + 1))
                continue
            step = 1
            base = part
            if "/" in part:
                base, _, step_str = part.partition("/")
                try:
                    step = int(step_str)
                except ValueError:
                    raise CronExpressionError(f"invalid step in {name}: {part}")
                if step <= 0:
                    raise CronExpressionError(f"invalid step in {name}: {part}")
            if base == "*":
                lo, hi = low, high
            elif "-" in base:
                lo_s, _, hi_s = base.partition("-")
                try:
                    lo, hi = int(lo_s), int(hi_s)
                except ValueError:
                    raise CronExpressionError(f"invalid range in {name}: {part}")
            else:
                try:
                    lo = hi = int(base)
                except ValueError:
                    raise CronExpressionError(f"invalid value in {name}: {part}")
            if lo < low or hi > high or lo > hi:
                raise CronExpressionError(f"value out of range [{low}-{high}] in {name}: {part}")
            allowed.update(range(lo, hi + 1, step))
        if not allowed:
            raise CronExpressionError(f"empty {name} field")
        return cls(name=name, allowed=allowed, expr=field)

    def match(self, value: int) -> bool:
        """匹配定时任务字段。

        Args:
            value: 待处理值。

        Returns:
            操作是否成功。
        """
        return value in self.allowed


# 常量：WEEKDAY_SUNDAY_ALIAS。
WEEKDAY_SUNDAY_ALIAS = 7


class CronSchedule:
    """定时任务调度相关组件。"""

    FIELDS = (
        ("minute", 0, 59),
        ("hour", 0, 23),
        ("day-of-month", 1, 31),
        ("month", 1, 12),
        ("day-of-week", 0, 7),
    )

    def __init__(self, expression: str) -> None:
        """初始化 CronSchedule。

        Args:
            expression: 表达式。

        Raises:
            CronExpressionError: 操作无法完成时抛出。
        """
        parts = expression.split() if isinstance(expression, str) else []
        if len(parts) != 5:
            raise CronExpressionError(f"cron expression must have 5 fields, got {len(parts)!r}")
        self.raw = expression
        self.minute = CronField.parse("minute", parts[0], 0, 59)
        self.hour = CronField.parse("hour", parts[1], 0, 23)
        self.day_of_month = CronField.parse("day-of-month", parts[2], 1, 31)
        self.month = CronField.parse("month", parts[3], 1, 12)
        self.day_of_week = CronField.parse("day-of-week", parts[4], 0, 7)

    def _dom_restricted(self) -> bool:
        """判断受限是否成立。

        Returns:
            操作是否成功。
        """
        return len(self.day_of_month.allowed) < 31

    def _dow_restricted(self) -> bool:
        """判断受限是否成立。

        Returns:
            操作是否成功。
        """
        return len(self.day_of_week.allowed) < 8

    def matches(self, dt: datetime) -> bool:
        """判断匹配结果是否成立。

        Args:
            dt: 输入参数。

        Returns:
            操作是否成功。
        """
        if dt.minute not in self.minute.allowed:
            return False
        if dt.hour not in self.hour.allowed:
            return False
        if dt.month not in self.month.allowed:
            return False
        dom_ok = dt.day in self.day_of_month.allowed
        weekday = dt.weekday()
        dow_value = (weekday + 1) % 7
        dow_ok = dow_value in self.day_of_week.allowed or (
            dow_value == 0 and WEEKDAY_SUNDAY_ALIAS in self.day_of_week.allowed
        )
        dom_restr = self._dom_restricted()
        dow_restr = self._dow_restricted()
        if dom_restr and dow_restr:
            return dom_ok or dow_ok
        if dom_restr:
            return dom_ok
        if dow_restr:
            return dow_ok
        return True

    def next_after(self, after: datetime, *, tzinfo=timezone.utc) -> datetime | None:
        """处理下一个之后。

        Args:
            after: 之后。
            tzinfo: 输入参数。

        Returns:
            无结果。
        """
        horizon_days = 5 * 366
        candidate = after.astimezone(tzinfo).replace(second=0, microsecond=0)
        for _ in range(horizon_days * 24 * 60):
            candidate = candidate + _ONE_MINUTE
            if self.matches(candidate):
                return candidate
        return None

    def next_run_from(self, last_run: datetime | None, now: datetime) -> datetime:
        """处理下一个运行从。

        Args:
            last_run: 运行。
            now: 输入参数。

        Returns:
            处理结果对象。

        Raises:
            CronExpressionError: 操作无法完成时抛出。
        """
        base = last_run or now
        nxt = self.next_after(base)
        if nxt is None:
            raise CronExpressionError(f"no matching date for cron {self.raw!r}")
        return nxt


# 常量：_ONE_MINUTE。
_ONE_MINUTE = timedelta(minutes=1)


def is_cron_cadence(cadence: str) -> bool:
    """判断定时任务周期是否成立。

    Args:
        cadence: 周期。

    Returns:
        操作是否成功。
    """
    if not isinstance(cadence, str):
        return False
    parts = cadence.split()
    return len(parts) == 5 and any(any(ch in p for ch in "*,-/") for p in parts)
