from __future__ import annotations

from agentforge.platform.domain.model import ModelProfile


class ModelRouter:
    def __init__(self, profiles: list[ModelProfile]) -> None:
        if not profiles:
            raise ValueError("At least one model profile is required")
        self._profiles = profiles

    def select(self, task_type: str = "general", strategy: str = "balanced") -> ModelProfile:
        candidates = [profile for profile in self._profiles if profile.is_available]
        if not candidates:
            raise ValueError("No available model profiles")
        specialized = [profile for profile in candidates if task_type in profile.task_types]
        if specialized:
            candidates = specialized
        if strategy == "cheapest":
            return min(candidates, key=lambda profile: profile.cost_per_1k_tokens)
        if strategy == "fastest":
            return min(candidates, key=lambda profile: profile.avg_latency_ms)
        if strategy == "capable":
            return max(candidates, key=lambda profile: profile.capability_score)
        return max(
            candidates,
            key=lambda profile: profile.capability_score - profile.cost_per_1k_tokens,
        )
