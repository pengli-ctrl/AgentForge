"""AgentForge 平台领域模型层：cron。

本模块定义 cron 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：CronExpressionError、CronField、CronSchedule。
- 主要函数：is_cron_cadence。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Collection


class CronExpressionError(ValueError):
    """CronExpressionError。

    CronExpressionError 封装相关领域行为，保持职责单一并降低调用方复杂度。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """


@dataclass(frozen=True)
class CronField:
    """CronField。

    CronField 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - name: str。
    - allowed: Collection[int]。
    - expr: str。
    - 方法 parse()。
    - 方法 match()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    name: str
    allowed: Collection[int]
    expr: str

    @classmethod
    def parse(cls, name: str, field: str, low: int, high: int) -> "CronField":
        """执行 parse 对应的逻辑，并返回处理结果。

        Args:
            name: str，调用方传入的 name 参数。
            field: str，调用方传入的 field 参数。
            low: int，调用方传入的 low 参数。
            high: int，调用方传入的 high 参数。

        Returns:
            'CronField'，函数执行后的结果。

        Raises:
            CronExpressionError: 当输入、状态或外部依赖不满足要求时抛出。
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
        """执行 match 对应的逻辑，并返回处理结果。

        Args:
            value: int，调用方传入的 value 参数。

        Returns:
            bool，函数执行后的结果。
        """
        return value in self.allowed


# 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
# 常量：WEEKDAY_SUNDAY_ALIAS。
WEEKDAY_SUNDAY_ALIAS = 7


class CronSchedule:
    """CronSchedule。

    CronSchedule 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - FIELDS: (('minute', 0, 59), ('hour', 0, 23), ('day-of-month', 1, 31), ('month', 1, 12),
    ('day-of-week', 0, 7))。
    - 方法 matches()。
    - 方法 next_after()。
    - 方法 next_run_from()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    FIELDS = (
        ("minute", 0, 59),
        ("hour", 0, 23),
        ("day-of-month", 1, 31),
        ("month", 1, 12),
        ("day-of-week", 0, 7),
    )

    def __init__(self, expression: str) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            expression: str，调用方传入的 expression 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            CronExpressionError: 当输入、状态或外部依赖不满足要求时抛出。
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
        """执行 _dom_restricted 对应的逻辑，并返回处理结果。

        Returns:
            bool，函数执行后的结果。
        """
        return len(self.day_of_month.allowed) < 31

    def _dow_restricted(self) -> bool:
        """执行 _dow_restricted 对应的逻辑，并返回处理结果。

        Returns:
            bool，函数执行后的结果。
        """
        return len(self.day_of_week.allowed) < 8

    def matches(self, dt: datetime) -> bool:
        """执行 matches 对应的逻辑，并返回处理结果。

        Args:
            dt: datetime，调用方传入的 dt 参数。

        Returns:
            bool，函数执行后的结果。
        """
        if dt.minute not in self.minute.allowed:
            return False
        if dt.hour not in self.hour.allowed:
            return False
        if dt.month not in self.month.allowed:
            return False
        dom_ok = dt.day in self.day_of_month.allowed
        weekday = dt.weekday()  # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        dow_value = (weekday + 1) % 7  # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        dow_ok = dow_value in self.day_of_week.allowed or (
            dow_value == 0 and WEEKDAY_SUNDAY_ALIAS in self.day_of_week.allowed
        )
        dom_restr = self._dom_restricted()
        dow_restr = self._dow_restricted()
        if dom_restr and dow_restr:
            # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
            return dom_ok or dow_ok
        if dom_restr:
            return dom_ok
        if dow_restr:
            return dow_ok
        return True

    def next_after(self, after: datetime, *, tzinfo=timezone.utc) -> datetime | None:
        """执行 next_after 对应的逻辑，并返回处理结果。

        Args:
            after: datetime，调用方传入的 after 参数。
            tzinfo: Any，调用方传入的 tzinfo 参数。

        Returns:
            datetime | None，函数执行后的结果。
        """
        horizon_days = 5 * 366
        candidate = after.astimezone(tzinfo).replace(second=0, microsecond=0)
        for _ in range(horizon_days * 24 * 60):
            candidate = candidate + _ONE_MINUTE
            if self.matches(candidate):
                return candidate
        return None

    def next_run_from(self, last_run: datetime | None, now: datetime) -> datetime:
        """执行 next_run_from 对应的逻辑，并返回处理结果。

        Args:
            last_run: datetime | None，调用方传入的 last_run 参数。
            now: datetime，调用方传入的 now 参数。

        Returns:
            datetime，函数执行后的结果。

        Raises:
            CronExpressionError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        base = last_run or now
        nxt = self.next_after(base)
        if nxt is None:
            raise CronExpressionError(f"no matching date for cron {self.raw!r}")
        return nxt


# 常量：_ONE_MINUTE。
_ONE_MINUTE = timedelta(minutes=1)


def is_cron_cadence(cadence: str) -> bool:
    """执行 is_cron_cadence 对应的逻辑，并返回处理结果。

    Args:
        cadence: str，调用方传入的 cadence 参数。

    Returns:
        bool，函数执行后的结果。
    """
    if not isinstance(cadence, str):
        return False
    parts = cadence.split()
    return len(parts) == 5 and any(any(ch in p for ch in "*,-/") for p in parts)
