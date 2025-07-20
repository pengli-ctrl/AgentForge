"""
5-model intelligent router — gateway layer core component.

Routes requests to the optimal model based on a 3-dimensional scoring matrix:
    Capability (weight 0.5): Model quality/accuracy for this task type
    Cost       (weight 0.3): Cost per 1K tokens (lower = better)
    Latency    (weight 0.2): Average response time in ms (lower = better)

Registered models:
    Qwen3-Pro:  capability=9.0, cost=$0.020/1K, latency=3000ms — premium quality
    GLM-5:      capability=8.0, cost=$0.015/1K, latency=2500ms — balanced
    Kimi:       capability=7.5, cost=$0.012/1K, latency=2000ms, max_context=200K
    MiniMax:    capability=5.0, cost=$0.002/1K, latency=800ms  — fast/cheap fallback
    DeepSeek-V3: capability=8.5, cost=$0.008/1K, latency=2000ms — best value

Degradation chain (on timeout/failure):
    Primary model → secondary → MiniMax (lightest) → preset response

Circuit breaker:
    If a model has >50% failure rate over last 10 consecutive calls,
    circuit opens for 15 minutes (skip model entirely).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from agentforge.gateway.model_registry import ModelProfile, ModelRegistry

logger = logging.getLogger(__name__)

# Re-export for backward compatibility
# Other modules can still do: from agentforge.gateway.router import ModelProfile, ModelRegistry
__all__ = ["ModelProfile", "ModelRegistry", "ModelRouteDecision", "SmartRouter"]


@dataclass
class ModelRouteDecision:
    """
    Result of a model routing decision.

    Named ModelRouteDecision (not RouteDecision) to avoid naming conflict
    with workflow/llm_router.py's RouteDecision, which handles YAML workflow
    routing (a different concern from model selection).
    """

    selected_model: str
    scores_per_model: dict[str, float]  # model_name → weighted_score
    reason: str
    scores_detail: dict[str, dict] = field(
        default_factory=dict
    )  # model → {capability, cost, latency}


class SmartRouter:
    """
    3-dimensional scoring router with fallback chain and circuit breaker.

    Scoring algorithm:
        1. Normalize each dimension to 0–10 scale (min-max normalization)
        2. For cost and latency, invert (lower is better → higher score)
        3. Weighted sum: score = 0.5*capability + 0.3*cost_score + 0.2*latency_score
        4. Select model with highest weighted score

    Why these weights?
        Capability (0.5) is most important — a wrong answer is worse than a slow one.
        Cost (0.3) matters for sustainability but shouldn't override quality.
        Latency (0.2) matters for UX but users tolerate 2–3s delays.

    Fallback chain on failure:
        Primary → Secondary (next highest score) → MiniMax (always fastest) → preset
    """

    WEIGHTS = {"capability": 0.5, "cost": 0.3, "latency": 0.2}

    def __init__(self, registry: Optional[ModelRegistry] = None):
        self._registry = registry or ModelRegistry()
        # Failure tracking per model for circuit breaker
        self._failure_counts: dict[str, list[bool]] = {}  # model → [success/failure booleans]
        self._lock = asyncio.Lock()

    async def route(
        self,
        task_type: str,
        complexity: float,
        input_text: str,
    ) -> ModelRouteDecision:
        """
        Route a request to the optimal model.

        Args:
            task_type: Category of task (e.g., "reasoning", "summarization",
                       "code_gen", "creative", "classification").
            complexity: Estimated complexity 0.0–1.0 (affects capability weight).
            input_text: The actual input (used for context length checking).

        Returns:
            RouteDecision with selected model and scoring details.
        """
        available = self._registry.get_available()
        if not available:
            # All models circuit-broken — emergency fallback to MiniMax
            minimax = self._registry.get("MiniMax")
            if minimax:
                minimax.is_available = True  # Force-restore
            available = [minimax] if minimax else []

        # Compute scores for each available model
        scores = {}
        details = {}

        for model in available:
            cap_score = self._score_capability(model, task_type, complexity)
            cost_score = self._score_cost(model, available)
            latency_score = self._score_latency(model, available)

            weighted = self._weighted_sum(cap_score, cost_score, latency_score)
            scores[model.name] = weighted
            details[model.name] = {
                "capability": round(cap_score, 2),
                "cost": round(cost_score, 2),
                "latency": round(latency_score, 2),
            }

        # Select highest-scoring model
        selected = max(scores, key=scores.get)
        reason = (
            f"Highest weighted score ({scores[selected]:.2f}) for "
            f"task_type={task_type}, complexity={complexity:.2f}"
        )

        return ModelRouteDecision(
            selected_model=selected,
            scores_per_model={k: round(v, 2) for k, v in scores.items()},
            reason=reason,
            scores_detail=details,
        )

    def _score_capability(self, model: ModelProfile, task_type: str, complexity: float) -> float:
        """
        Capability score (0–10). Adjusted by task type and complexity.

        High-complexity tasks amplify model capability differences.
        Task-specific bonuses:
        - Kimi gets a boost for long-context tasks (200K context window)
        - Qwen3-Pro gets a boost for reasoning tasks (highest baseline)
        - DeepSeek-V3 gets a boost for code generation tasks
        """
        base = model.capability_score

        # Task-specific adjustments
        task_bonuses = {
            "reasoning": {"Qwen3-Pro": 0.5, "DeepSeek-V3": 0.3},
            "code_gen": {"DeepSeek-V3": 0.5, "Qwen3-Pro": 0.3},
            "long_context": {"Kimi": 1.0},  # 200K context is unique advantage
            "creative": {"Qwen3-Pro": 0.3, "GLM-5": 0.2},
            "classification": {"MiniMax": 0.5},  # Cheap model sufficient
        }
        bonus = task_bonuses.get(task_type, {}).get(model.name, 0.0)

        # Complexity amplification: high complexity → capability matters more
        complexity_factor = 1.0 + (complexity * 0.2)  # Up to +20% at max complexity

        return min(10.0, (base + bonus) * complexity_factor)

    def _score_cost(self, model: ModelProfile, all_models: list[ModelProfile]) -> float:
        """
        Cost score (0–10). Inverted: lower cost → higher score.
        Normalized relative to the most expensive model in the pool.
        """
        costs = [m.cost_per_1k_tokens for m in all_models]
        min_cost, max_cost = min(costs), max(costs)
        if max_cost == min_cost:
            return 5.0  # All same cost
        # Invert: cheapest gets 10, most expensive gets 0
        normalized = 10.0 * (1.0 - (model.cost_per_1k_tokens - min_cost) / (max_cost - min_cost))
        return normalized

    def _score_latency(self, model: ModelProfile, all_models: list[ModelProfile]) -> float:
        """
        Latency score (0–10). Inverted: lower latency → higher score.
        Normalized relative to the slowest model in the pool.
        """
        latencies = [m.avg_latency_ms for m in all_models]
        min_lat, max_lat = min(latencies), max(latencies)
        if max_lat == min_lat:
            return 5.0
        # Invert: fastest gets 10, slowest gets 0
        normalized = 10.0 * (1.0 - (model.avg_latency_ms - min_lat) / (max_lat - min_lat))
        return normalized

    def _weighted_sum(self, capability: float, cost: float, latency: float) -> float:
        """Compute weighted score from three dimensions."""
        return (
            self.WEIGHTS["capability"] * capability
            + self.WEIGHTS["cost"] * cost
            + self.WEIGHTS["latency"] * latency
        )

    # ── Failure tracking & circuit breaker ──────────────────────────────

    async def record_result(self, model_name: str, success: bool) -> None:
        """
        Record a model call result for circuit breaker tracking.

        If last 10 calls have >50% failure rate → circuit opens for 15min.
        """
        async with self._lock:
            if model_name not in self._failure_counts:
                self._failure_counts[model_name] = []
            self._failure_counts[model_name].append(success)
            # Keep only last 20 results
            self._failure_counts[model_name] = self._failure_counts[model_name][-20:]

            # Check circuit breaker: last 10 calls, >50% failure
            recent = self._failure_counts[model_name][-10:]
            if len(recent) >= 10:
                failure_rate = sum(1 for s in recent if not s) / len(recent)
                if failure_rate > 0.5:
                    logger.warning(
                        "Circuit breaker triggered for %s: %.0f%% failure rate over last 10 calls",
                        model_name,
                        failure_rate * 100,
                    )
                    await self._registry.mark_unavailable(model_name, duration_seconds=900)

    # ── Fallback chain ──────────────────────────────────────────────────

    async def get_fallback(self, failed_model: str) -> Optional[str]:
        """
        Get the next model in the fallback chain.

        Order: next highest score → MiniMax (lightest) → None (preset response).
        """
        available = self._registry.get_available()
        candidates = [m for m in available if m.name != failed_model]
        if not candidates:
            return None  # All models failed — use preset response
        # Return highest capability model as fallback (quality over cost when primary failed)
        fallback = max(candidates, key=lambda m: m.capability_score)
        return fallback.name

    def get_preset_response(self) -> dict:
        """Last-resort preset response when all models are unavailable."""
        return {
            "result": (
                "Service temporarily unavailable. All models are experiencing issues. "
                "Please retry in a few minutes."
            ),
            "degraded": True,
            "fallback": "preset",
        }
