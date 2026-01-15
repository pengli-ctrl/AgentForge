"""AgentForge 模型网关层：cost_tracker。

本模块负责 cost_tracker 相关能力，是 模型网关层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：AlertLevel、CostRecord、CostReport、CostTracker。
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """AlertLevel。

    AlertLevel 是状态或类型枚举，用于约束系统内部取值，避免散落的字符串常量。

    主要成员：
    - P3_DAILY: 3。
    - P2_WARNING: 2。
    - P1_ALERT: 1。
    - P0_CRITICAL: 0。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    P3_DAILY = 3  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    P2_WARNING = 2  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    P1_ALERT = 1  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    P0_CRITICAL = 0  # 说明：该步骤用于实现上述逻辑并保证行为稳定。


@dataclass
class CostRecord:
    """CostRecord。

    CostRecord 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - timestamp: float。
    - model_name: str。
    - token_count: int。
    - cost: float。
    - correlation_id: str。
    - agent_name: str。
    - span_id: str。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    timestamp: float
    model_name: str
    token_count: int
    cost: float
    correlation_id: str = ""  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    agent_name: str = ""  # Agent 注册与查询。
    span_id: str = ""  # 说明：该步骤用于实现上述逻辑并保证行为稳定。


@dataclass
class CostReport:
    """CostReport。

    CostReport 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - date: str。
    - total_cost: float。
    - total_tokens: int。
    - budget_limit: float。
    - budget_usage_pct: float。
    - model_breakdown: dict[str, dict]。
    - agent_breakdown: dict[str, dict]。
    - alerts_triggered: list[str]。
    - cache_hits_saved: float。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    date: str
    total_cost: float
    total_tokens: int
    budget_limit: float
    budget_usage_pct: float
    model_breakdown: dict[str, dict]  # 成本统计。
    agent_breakdown: dict[str, dict]  # Agent 注册与查询。
    alerts_triggered: list[str]
    cache_hits_saved: float = 0.0  # 缓存处理。


class CostTracker:
    """CostTracker。

    CostTracker 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - P0_THRESHOLD: 1.0。
    - P1_THRESHOLD: 0.9。
    - P2_THRESHOLD: 0.7。
    - 方法 record()。
    - 方法 get_total_cost()。
    - 方法 get_budget_usage()。
    - 方法 is_budget_exhausted()。
    - 方法 daily_report()。
    - 方法 get_cost_by_correlation()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    P0_THRESHOLD = 1.00  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    P1_THRESHOLD = 0.90  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    P2_THRESHOLD = 0.70  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
    # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    def __init__(self, daily_budget: float = 100.0):
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            daily_budget: float，调用方传入的 daily_budget 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._daily_budget = daily_budget
        self._lock = asyncio.Lock()

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._records: list[CostRecord] = []
        self._daily_start: float = self._today_start()
        self._current_day: str = time.strftime("%Y-%m-%d")

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self._total_cost: float = 0.0
        self._total_tokens: int = 0
        self._model_totals: dict[str, dict] = {}  # 成本统计。
        self._agent_totals: dict[str, dict] = {}  # Agent 注册与查询。

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
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
        """执行 record 对应的逻辑，并返回处理结果。

        Args:
            token_count: int，调用方传入的 token_count 参数。
            model_name: str，调用方传入的 model_name 参数。
            cost: float，调用方传入的 cost 参数。
            correlation_id: str，调用方传入的 correlation_id 参数。
            agent_name: str，调用方传入的 agent_name 参数。
            span_id: str，调用方传入的 span_id 参数。

        Returns:
            None，函数执行后的结果。
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

            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            self._total_cost += cost
            self._total_tokens += token_count

            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            if model_name not in self._model_totals:
                self._model_totals[model_name] = {"cost": 0, "tokens": 0, "calls": 0}
            self._model_totals[model_name]["cost"] += cost
            self._model_totals[model_name]["tokens"] += token_count
            self._model_totals[model_name]["calls"] += 1

            # Agent 注册与查询。
            if agent_name:
                if agent_name not in self._agent_totals:
                    self._agent_totals[agent_name] = {"cost": 0, "tokens": 0, "calls": 0}
                self._agent_totals[agent_name]["cost"] += cost
                self._agent_totals[agent_name]["tokens"] += token_count
                self._agent_totals[agent_name]["calls"] += 1

            # 说明：该步骤用于实现上述逻辑并保证行为稳定。
            await self._check_alerts()

    async def _check_alerts(self) -> None:
        """执行 _check_alerts 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
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
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            float，函数执行后的结果。
        """
        return self._total_cost

    def get_budget_usage(self) -> float:
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            float，函数执行后的结果。
        """
        if self._daily_budget <= 0:
            return 0.0
        return self._total_cost / self._daily_budget

    def is_budget_exhausted(self) -> bool:
        """执行 is_budget_exhausted 对应的逻辑，并返回处理结果。

        Returns:
            bool，函数执行后的结果。
        """
        return self._p0_triggered

    async def daily_report(self) -> CostReport:
        """执行 daily_report 对应的逻辑，并返回处理结果。

        Returns:
            CostReport，函数执行后的结果。
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
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            correlation_id: str，调用方传入的 correlation_id 参数。

        Returns:
            dict，函数执行后的结果。
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
        """执行 _rollover_if_new_day 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
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
        """执行 _today_start 对应的逻辑，并返回处理结果。

        Returns:
            float，函数执行后的结果。
        """
        import datetime

        now = datetime.datetime.now()
        start = datetime.datetime(now.year, now.month, now.day)
        return start.timestamp()
