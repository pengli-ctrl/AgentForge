"""成本模块。"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """成本告警级别枚举。"""

    P3_DAILY = 3
    P2_WARNING = 2
    P1_ALERT = 1
    P0_CRITICAL = 0


@dataclass
class CostRecord:
    """成本记录持久化模型。

    Attributes:
        timestamp: 字段值。
        model_name: 模型名称。
        token_count: 令牌数量。
        cost: 成本。
        correlation_id: 用于关联同一业务链路的关联 ID。
        agent_name: 智能体名称。
        span_id: 链路片段ID。
    """

    timestamp: float
    model_name: str
    token_count: int
    cost: float
    correlation_id: str = ""
    agent_name: str = ""
    span_id: str = ""


@dataclass
class CostReport:
    """成本报告领域组件。

    Attributes:
        date: 字段值。
        total_cost: 总计成本。
        total_tokens: 总计。
        budget_limit: 预算限制。
        budget_usage_pct: 预算用量。
        model_breakdown: 模型。
        agent_breakdown: 智能体。
        alerts_triggered: 告警。
        cache_hits_saved: 缓存。
    """

    date: str
    total_cost: float
    total_tokens: int
    budget_limit: float
    budget_usage_pct: float
    model_breakdown: dict[str, dict]  # 成本统计。
    agent_breakdown: dict[str, dict]
    alerts_triggered: list[str]
    cache_hits_saved: float = 0.0  # 缓存处理。


class CostTracker:
    """成本使用量跟踪器。"""

    P0_THRESHOLD = 1.00
    P1_THRESHOLD = 0.90
    P2_THRESHOLD = 0.70

    def __init__(self, daily_budget: float = 100.0):
        """初始化 CostTracker。

        Args:
            daily_budget: 每日预算。
        """
        self._daily_budget = daily_budget
        self._lock = asyncio.Lock()

        self._records: list[CostRecord] = []
        self._daily_start: float = self._today_start()
        self._current_day: str = time.strftime("%Y-%m-%d")

        self._total_cost: float = 0.0
        self._total_tokens: int = 0
        self._model_totals: dict[str, dict] = {}  # 成本统计。
        self._agent_totals: dict[str, dict] = {}

        self._alerts: list[dict] = []
        self._p0_triggered: bool = False

    async def record(
        self,
        token_count: int,
        model_name: str,
        cost: float,
        correlation_id: str = "",
        agent_name: str = "",
        span_id: str = "",
    ) -> None:
        """记录成本。

        Args:
            token_count: 令牌数量。
            model_name: 模型名称。
            cost: 成本。
            correlation_id: 用于关联同一业务链路的关联 ID。
            agent_name: 智能体名称。
            span_id: 链路片段 ID。
        """
        async with self._lock:
            self._rollover_if_new_day()

            record = CostRecord(
                timestamp=time.time(),
                model_name=model_name,
                token_count=token_count,
                cost=cost,
                correlation_id=correlation_id,
                agent_name=agent_name,
                span_id=span_id,
            )
            self._records.append(record)

            self._total_cost += cost
            self._total_tokens += token_count

            if model_name not in self._model_totals:
                self._model_totals[model_name] = {"cost": 0, "tokens": 0, "calls": 0}
            self._model_totals[model_name]["cost"] += cost
            self._model_totals[model_name]["tokens"] += token_count
            self._model_totals[model_name]["calls"] += 1

            if agent_name:
                if agent_name not in self._agent_totals:
                    self._agent_totals[agent_name] = {"cost": 0, "tokens": 0, "calls": 0}
                self._agent_totals[agent_name]["cost"] += cost
                self._agent_totals[agent_name]["tokens"] += token_count
                self._agent_totals[agent_name]["calls"] += 1

            await self._check_alerts()

    async def _check_alerts(self) -> None:
        """检查告警。"""
        usage_pct = self._total_cost / self._daily_budget if self._daily_budget > 0 else 0

        if usage_pct >= self.P0_THRESHOLD and not self._p0_triggered:
            self._p0_triggered = True
            alert = {
                "level": AlertLevel.P0_CRITICAL,
                "timestamp": time.time(),
                "message": (
                    f"P0 CRITICAL: Budget 100% exhausted "
                    f"(${self._total_cost:.2f}/${self._daily_budget:.2f}). Stopping service."
                ),
            }
            self._alerts.append(alert)
            logger.critical(alert["message"])

        elif usage_pct >= self.P1_THRESHOLD:
            # 就绪状态。
            if not any(a["level"] == AlertLevel.P1_ALERT for a in self._alerts[-5:]):
                alert = {
                    "level": AlertLevel.P1_ALERT,
                    "timestamp": time.time(),
                    "message": (
                        f"P1 ALERT: Budget at {usage_pct:.0%} "
                        f"(${self._total_cost:.2f}/${self._daily_budget:.2f}). Throttling enabled."
                    ),
                }
                self._alerts.append(alert)
                logger.warning(alert["message"])

        elif usage_pct >= self.P2_THRESHOLD:
            if not any(a["level"] == AlertLevel.P2_WARNING for a in self._alerts[-5:]):
                alert = {
                    "level": AlertLevel.P2_WARNING,
                    "timestamp": time.time(),
                    "message": (
                        f"P2 WARNING: Budget at {usage_pct:.0%} "
                        f"(${self._total_cost:.2f}/${self._daily_budget:.2f}). Review usage."
                    ),
                }
                self._alerts.append(alert)
                logger.info(alert["message"])

    def get_total_cost(self) -> float:
        """读取总计成本。

        Returns:
            数值结果。
        """
        return self._total_cost

    def get_budget_usage(self) -> float:
        """获取预算用量。

        Returns:
            数值结果。
        """
        if self._daily_budget <= 0:
            return 0.0
        return self._total_cost / self._daily_budget

    def is_budget_exhausted(self) -> bool:
        """判断预算是否已经耗尽。

        Returns:
            操作是否成功。
        """
        return self._p0_triggered

    async def daily_report(self) -> CostReport:
        """生成每日报告。

        Returns:
            成本报告结果。
        """
        self._rollover_if_new_day()

        return CostReport(
            date=self._current_day,
            total_cost=round(self._total_cost, 4),
            total_tokens=self._total_tokens,
            budget_limit=self._daily_budget,
            budget_usage_pct=round(self.get_budget_usage(), 4),
            model_breakdown={
                model: {k: round(v, 4) if isinstance(v, float) else v for k, v in data.items()}
                for model, data in self._model_totals.items()
            },
            agent_breakdown={
                agent: {k: round(v, 4) if isinstance(v, float) else v for k, v in data.items()}
                for agent, data in self._agent_totals.items()
            },
            alerts_triggered=[a["message"] for a in self._alerts],
        )

    async def get_cost_by_correlation(self, correlation_id: str) -> dict:
        """获取成本由关联。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。

        Returns:
            结构化结果字典。
        """
        records = [r for r in self._records if r.correlation_id == correlation_id]
        if not records:
            return {"total_cost": 0, "total_tokens": 0, "calls": 0}
        return {
            "total_cost": sum(r.cost for r in records),
            "total_tokens": sum(r.token_count for r in records),
            "calls": len(records),
            "models_used": list(set(r.model_name for r in records)),
        }

    def _rollover_if_new_day(self) -> None:
        """切换成本。"""
        today = time.strftime("%Y-%m-%d")
        if today != self._current_day:
            self._current_day = today
            self._records.clear()
            self._total_cost = 0.0
            self._total_tokens = 0
            self._model_totals.clear()
            self._agent_totals.clear()
            self._alerts.clear()
            self._p0_triggered = False
            self._daily_start = self._today_start()

    @staticmethod
    def _today_start() -> float:
        """获取今日开始。

        Returns:
            数值结果。
        """
        import datetime

        now = datetime.datetime.now()
        start = datetime.datetime(now.year, now.month, now.day)
        return start.timestamp()
