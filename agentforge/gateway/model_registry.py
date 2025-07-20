"""
Model Registry — central registry for available LLM models.

Manages model profiles, availability status, and circuit breaker state.
Each model has a ModelProfile describing its capabilities, cost, and latency.
The registry is the source of truth for which models the SmartRouter can use.

Design decisions:
    - Singleton-style: one registry instance shared across the gateway layer
    - Circuit breaker is tracked HERE, not in the router — the router calls
      registry.mark_unavailable() when failures exceed threshold
    - Recovery is automatic via call_later (no background thread needed)
    - Default models are registered at init with production-tuned profiles
    - Models can be added/removed at runtime for A/B testing or model rotation

Production tuning notes:
    - Qwen3-Pro: highest capability (9.0), but 2.5x more expensive than MiniMax
    - Kimi: unique 200K context window — only model for long-document tasks
    - MiniMax: 10x cheaper than alternatives, used as fallback and for simple tasks
    - DeepSeek-V3: best price/performance ratio — 0.008/1K with 8.5 capability
    - GLM-5: balanced middle-ground, good for general-purpose tasks
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelProfile:
    """
    Profile for a single registered model.

    All scoring dimensions are stored here; routing logic is in SmartRouter.
    The profile is essentially a static description of the model's capabilities
    and economics — runtime state (is_available) is also tracked here.

    Attributes:
        name: Model identifier (e.g., "Qwen3-Pro"). Used in API calls.
        capability_score: Quality score 0–10, higher = better output quality.
        cost_per_1k_tokens: USD cost per 1000 tokens (input+output combined).
        avg_latency_ms: Average response latency measured over last 1000 calls.
        max_context_length: Maximum input token count the model supports.
        is_available: Runtime flag — False when circuit breaker is open.
        description: Human-readable model description for logging/debugging.
        specializations: Task types this model excels at (e.g., ["reasoning", "code_gen"]).
    """

    name: str
    capability_score: float  # 0–10, higher = better quality
    cost_per_1k_tokens: float  # USD per 1K tokens
    avg_latency_ms: float  # Average response latency
    max_context_length: int = 32000  # Max input tokens
    is_available: bool = True  # Runtime: set False during circuit break
    description: str = ""
    specializations: list[str] = field(default_factory=list)


class ModelRegistry:
    """
    Central registry of available LLM models.

    Responsibilities:
        1. Maintain the list of models and their profiles
        2. Track availability (circuit breaker state) per model
        3. Provide lookup methods for the SmartRouter
        4. Handle automatic recovery after circuit breaker trips

    Circuit breaker behavior:
        - When a model has >50% failure rate over last 10 calls, the
          SmartRouter calls mark_unavailable() to temporarily remove it
        - After duration_seconds (default 15 min), the model is automatically
          recovered and becomes available again
        - This prevents cascading failures from a degraded model provider

    Thread safety:
        - All mutations (mark_unavailable, register, unregister) use asyncio.Lock
        - Read operations (get, list_models, get_available) are lock-free
          because they return copies or immutable references
    """

    def __init__(self):
        self._models: dict[str, ModelProfile] = {}
        self._lock = asyncio.Lock()
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register the 5 default models with production-tuned profiles."""
        defaults = [
            ModelProfile(
                name="Qwen3-Pro",
                capability_score=9.0,
                cost_per_1k_tokens=0.020,
                avg_latency_ms=3000,
                max_context_length=32000,
                description="Premium quality, best for complex reasoning and creative tasks",
                specializations=["reasoning", "creative", "code_gen"],
            ),
            ModelProfile(
                name="GLM-5",
                capability_score=8.0,
                cost_per_1k_tokens=0.015,
                avg_latency_ms=2500,
                max_context_length=32000,
                description="Balanced general-purpose model",
                specializations=["reasoning", "creative"],
            ),
            ModelProfile(
                name="Kimi",
                capability_score=7.5,
                cost_per_1k_tokens=0.012,
                avg_latency_ms=2000,
                max_context_length=200000,  # 200K context — unique advantage
                description="200K context window — best for long-document processing",
                specializations=["long_context", "summarization"],
            ),
            ModelProfile(
                name="MiniMax",
                capability_score=5.0,
                cost_per_1k_tokens=0.002,
                avg_latency_ms=800,
                max_context_length=16000,
                description="Fast and cheap — ideal for simple tasks and fallback",
                specializations=["classification", "simple_extraction"],
            ),
            ModelProfile(
                name="DeepSeek-V3",
                capability_score=8.5,
                cost_per_1k_tokens=0.008,
                avg_latency_ms=2000,
                max_context_length=64000,
                description="Best price/performance ratio — excellent for code generation",
                specializations=["code_gen", "reasoning"],
            ),
        ]
        for model in defaults:
            self._models[model.name] = model

    def get(self, name: str) -> Optional[ModelProfile]:
        """
        Get a model profile by name.

        Args:
            name: Model identifier (e.g., "Qwen3-Pro").

        Returns:
            ModelProfile if found, None otherwise.
        """
        return self._models.get(name)

    def get_available(self) -> list[ModelProfile]:
        """
        Get all models currently available (not circuit-broken).

        Returns:
            List of ModelProfile instances where is_available=True.
        """
        return [m for m in self._models.values() if m.is_available]

    async def mark_unavailable(self, name: str, duration_seconds: float = 900) -> None:
        """
        Circuit breaker: mark model as unavailable for duration.

        Called by SmartRouter when a model's failure rate exceeds threshold.
        After duration_seconds, the model is automatically recovered.

        Args:
            name: Model identifier to mark unavailable.
            duration_seconds: How long to keep the circuit open. Default 900s (15 min).
        """
        async with self._lock:
            model = self._models.get(name)
            if model:
                model.is_available = False
                logger.warning("Circuit breaker: %s unavailable for %.0fs", name, duration_seconds)
                # Schedule automatic recovery
                asyncio.get_event_loop().call_later(duration_seconds, self._recover_model, name)

    def _recover_model(self, name: str) -> None:
        """
        Recover a circuit-broken model (called after timeout).

        This is invoked by call_later — it's synchronous because it's
        called from the event loop's timer, not from async code.
        """
        if name in self._models:
            self._models[name].is_available = True
            logger.info("Circuit breaker: %s recovered", name)

    async def register_model(self, profile: ModelProfile) -> None:
        """
        Register a new model at runtime (e.g., for A/B testing).

        Args:
            profile: Complete ModelProfile for the new model.
        """
        async with self._lock:
            if profile.name in self._models:
                logger.warning("Model '%s' already registered, overwriting", profile.name)
            self._models[profile.name] = profile
            logger.info(
                "Registered model: %s (capability=%.1f, cost=%.4f/1K)",
                profile.name,
                profile.capability_score,
                profile.cost_per_1k_tokens,
            )

    async def unregister_model(self, name: str) -> bool:
        """
        Remove a model from the registry.

        Args:
            name: Model identifier to remove.

        Returns:
            True if the model was found and removed.
        """
        async with self._lock:
            if name in self._models:
                del self._models[name]
                logger.info("Unregistered model: %s", name)
                return True
            return False

    def list_models(self) -> list[str]:
        """
        List all registered model names.

        Returns:
            List of model name strings (includes both available and circuit-broken).
        """
        return list(self._models.keys())

    def get_all_profiles(self) -> list[ModelProfile]:
        """
        Get all model profiles (including circuit-broken ones).
        Useful for admin/dashboard purposes.

        Returns:
            List of all ModelProfile instances.
        """
        return list(self._models.values())

    def get_by_specialization(self, task_type: str) -> list[ModelProfile]:
        """
        Get models that specialize in a given task type.

        Args:
            task_type: Task category (e.g., "code_gen", "reasoning").

        Returns:
            List of ModelProfile instances that list this specialization.
        """
        return [
            m for m in self._models.values() if m.is_available and task_type in m.specializations
        ]

    def get_cheapest(self) -> Optional[ModelProfile]:
        """Get the cheapest available model (for budget-sensitive routing)."""
        available = self.get_available()
        if not available:
            return None
        return min(available, key=lambda m: m.cost_per_1k_tokens)

    def get_fastest(self) -> Optional[ModelProfile]:
        """Get the fastest available model (for latency-sensitive routing)."""
        available = self.get_available()
        if not available:
            return None
        return min(available, key=lambda m: m.avg_latency_ms)

    def get_most_capable(self) -> Optional[ModelProfile]:
        """Get the most capable available model (for quality-critical tasks)."""
        available = self.get_available()
        if not available:
            return None
        return max(available, key=lambda m: m.capability_score)

    def status_summary(self) -> dict[str, Any]:
        """
        Get a status summary for monitoring/dashboard.

        Returns:
            Dict with model counts and availability status.
        """
        total = len(self._models)
        available = len(self.get_available())
        return {
            "total_models": total,
            "available": available,
            "circuit_broken": total - available,
            "models": {
                name: {
                    "available": m.is_available,
                    "capability": m.capability_score,
                    "cost_per_1k": m.cost_per_1k_tokens,
                    "latency_ms": m.avg_latency_ms,
                }
                for name, m in self._models.items()
            },
        }
