from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Collection


class CronExpressionError(ValueError):
    """Raised when a cron expression cannot be parsed."""


@dataclass(frozen=True)
class CronField:
    """A single cron field: allowed values within a 0-based/1-based range.

    Supports ``*``, ``*/step``, ``a-b`` ranges, ``a,b,c`` lists and plain
    single values. ``*`` means the whole range; values outside the inclusive
    range raise CronExpressionError.
    """

    name: str
    allowed: Collection[int]
    expr: str

    @classmethod
    def parse(cls, name: str, field: str, low: int, high: int) -> "CronField":
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
        return value in self.allowed


# day-of-week is 0 (Sunday) .. 6 (Saturday) with optional 7 == Sunday alias.
WEEKDAY_SUNDAY_ALIAS = 7


class CronSchedule:
    """A 5-field cron schedule: minute hour day-of-month month day-of-week.

    Semantics mirror Vixie cron:
    - ``minute`` 0-59, ``hour`` 0-23, ``day-of-month`` 1-31,
      ``month`` 1-12, ``day-of-week`` 0-7 (0 and 7 = Sunday).
    - When both day-of-month and day-of-week are restricted (non-``*``), a day
      matches if EITHER field matches (the classic cron OR rule).
    """

    FIELDS = (
        ("minute", 0, 59),
        ("hour", 0, 23),
        ("day-of-month", 1, 31),
        ("month", 1, 12),
        ("day-of-week", 0, 7),
    )

    def __init__(self, expression: str) -> None:
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
        return len(self.day_of_month.allowed) < 31

    def _dow_restricted(self) -> bool:
        return len(self.day_of_week.allowed) < 8

    def matches(self, dt: datetime) -> bool:
        if dt.minute not in self.minute.allowed:
            return False
        if dt.hour not in self.hour.allowed:
            return False
        if dt.month not in self.month.allowed:
            return False
        dom_ok = dt.day in self.day_of_month.allowed
        weekday = dt.weekday()  # Monday=0 .. Sunday=6
        dow_value = (weekday + 1) % 7  # Sunday->0, Monday->1 ... Saturday->6
        dow_ok = dow_value in self.day_of_week.allowed or (
            dow_value == 0 and WEEKDAY_SUNDAY_ALIAS in self.day_of_week.allowed
        )
        dom_restr = self._dom_restricted()
        dow_restr = self._dow_restricted()
        if dom_restr and dow_restr:
            # classic cron OR rule: match if either day field matches
            return dom_ok or dow_ok
        if dom_restr:
            return dom_ok
        if dow_restr:
            return dow_ok
        return True

    def next_after(self, after: datetime, *, tzinfo=timezone.utc) -> datetime | None:
        """Return the next match strictly after ``after``, or None if not found.

        Scans forward minute-by-minute over a bounded horizon (default 5 years)
        to stay dependency-free and predictable for the report scheduler.
        """
        horizon_days = 5 * 366
        candidate = after.astimezone(tzinfo).replace(second=0, microsecond=0)
        for _ in range(horizon_days * 24 * 60):
            candidate = candidate + _ONE_MINUTE
            if self.matches(candidate):
                return candidate
        return None

    def next_run_from(self, last_run: datetime | None, now: datetime) -> datetime:
        """Compute the next scheduled run after the latest run / now.

        If a schedule has never run, we schedule from ``now``; otherwise from
        the last successful run so the cadence anchors to actual progress.
        """
        base = last_run or now
        nxt = self.next_after(base)
        if nxt is None:
            raise CronExpressionError(f"no matching date for cron {self.raw!r}")
        return nxt


_ONE_MINUTE = timedelta(minutes=1)


def is_cron_cadence(cadence: str) -> bool:
    """True when a schedule cadence string looks like a 5-field cron expression."""
    if not isinstance(cadence, str):
        return False
    parts = cadence.split()
    return len(parts) == 5 and any(any(ch in p for ch in "*,-/") for p in parts)
