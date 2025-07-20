"""
Token-level cost tracking + P0–P3 four-level budget alerting.

    P0 (100%): Stop all new requests — budget exhausted
    P1 (90%):  Alert on-call — budget nearly exhausted, start throttling
    P2 (70%):  Warning — budget consumption accelerating, review usage
    P3 (daily): Daily report — routine cost accounting

Design rationale:
    Every LLM call costs money. Without per-token tracking, you can't:
    1. Attribute cost to specific DAGs/users/agents (cost allocation)
    2. Detect runaway loops (a stuck agent burning $100/hour)
    3. Forecast budget needs (daily/weekly/monthly trends)
    4. Enforce limits (stop service before bankrupting the account)

    The P0–P3 system is modeled after SRE alerting: P0 is page-the-on-call,
    P1 is urgent Slack message, P2 is tomorrow's standup topic, P3 is routine.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Budget alert levels, from least to most severe."""

    P3_DAILY = 3  # Routine daily report
    P2_WARNING = 2  # Budget consumption accelerating
    P1_ALERT = 1  # Budget nearly exhausted
    P0_CRITICAL = 0  # Budget exhausted — stop service


@dataclass
class CostRecord:
    """Single cost record from one LLM call."""

    timestamp: float
    model_name: str
    token_count: int
    cost: float
    correlation_id: str = ""  # Link to DAG execution
    agent_name: str = ""  # Which agent made the call
    span_id: str = ""  # Link to InferenceSpan


@dataclass
class CostReport:
    """Daily cost report with breakdowns."""

    date: str
    total_cost: float
    total_tokens: int
    budget_limit: float
    budget_usage_pct: float
    model_breakdown: dict[str, dict]  # model → {cost, tokens, calls}
    agent_breakdown: dict[str, dict]  # agent → {cost, tokens, calls}
    alerts_triggered: list[str]
    cache_hits_saved: float = 0.0  # Estimated savings from semantic cache


class CostTracker:
    """
    Token-level cost tracking with budget enforcement and alerting.

    Tracks every LLM call's cost, aggregates by model/agent/dag,
    and triggers alerts when budget thresholds are crossed.

    Thread safety: all mutations protected by asyncio.Lock since
    multiple DAG nodes may record costs concurrently.
    """

    # Budget thresholds (fraction of daily budget)
    P0_THRESHOLD = 1.00  # Stop service
    P1_THRESHOLD = 0.90  # Alert + throttle
    P2_THRESHOLD = 0.70  # Warning
    # P3 is always active (daily report)

    def __init__(self, daily_budget: float = 100.0):
        """
        Args:
            daily_budget: Maximum daily spend in USD. Default $100.
        """
        self._daily_budget = daily_budget
        self._lock = asyncio.Lock()

        # Tracking state
        self._records: list[CostRecord] = []
        self._daily_start: float = self._today_start()
        self._current_day: str = time.strftime("%Y-%m-%d")

        # Pre-computed indices for fast aggregation
        self._total_cost: float = 0.0
        self._total_tokens: int = 0
        self._model_totals: dict[str, dict] = {}  # model → {cost, tokens, calls}
        self._agent_totals: dict[str, dict] = {}  # agent → {cost, tokens, calls}

        # Alert history
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
        """
        Record a single LLM call's cost.

        Args:
            token_count: Total tokens (prompt + completion).
            model_name: Model used (for per-model cost tracking).
            cost: Cost in USD for this call.
            correlation_id: DAG execution ID for cost attribution.
            agent_name: Agent that triggered the call.
            span_id: InferenceSpan ID for trace correlation.
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

            # Update aggregates
            self._total_cost += cost
            self._total_tokens += token_count

            # Model breakdown
            if model_name not in self._model_totals:
                self._model_totals[model_name] = {"cost": 0, "tokens": 0, "calls": 0}
            self._model_totals[model_name]["cost"] += cost
            self._model_totals[model_name]["tokens"] += token_count
            self._model_totals[model_name]["calls"] += 1

            # Agent breakdown
            if agent_name:
                if agent_name not in self._agent_totals:
                    self._agent_totals[agent_name] = {"cost": 0, "tokens": 0, "calls": 0}
                self._agent_totals[agent_name]["cost"] += cost
                self._agent_totals[agent_name]["tokens"] += token_count
                self._agent_totals[agent_name]["calls"] += 1

            # Check budget thresholds
            await self._check_alerts()

    async def _check_alerts(self) -> None:
        """Check if any budget threshold has been crossed. Called under lock."""
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
            # Check if we already alerted at this level today
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
        """Get total cost for current day."""
        return self._total_cost

    def get_budget_usage(self) -> float:
        """Get budget usage as a fraction (0.0 to 1.0+)."""
        if self._daily_budget <= 0:
            return 0.0
        return self._total_cost / self._daily_budget

    def is_budget_exhausted(self) -> bool:
        """Check if P0 threshold has been crossed (service should stop)."""
        return self._p0_triggered

    async def daily_report(self) -> CostReport:
        """
        Generate daily cost report with full breakdowns.

        Returns:
            CostReport with model/agent breakdowns and alert history.
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
        """Get cost breakdown for a specific DAG execution."""
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
        """Reset daily counters if we've crossed midnight."""
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
        """Return timestamp for start of today (midnight)."""
        import datetime

        now = datetime.datetime.now()
        start = datetime.datetime(now.year, now.month, now.day)
        return start.timestamp()
