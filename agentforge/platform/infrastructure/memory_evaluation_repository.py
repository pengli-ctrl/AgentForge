from __future__ import annotations

from agentforge.platform.domain.evaluation import EvaluationSample


class MemoryEvaluationRepository:
    def __init__(self) -> None:
        self.samples: list[EvaluationSample] = []

    async def save(self, sample: EvaluationSample) -> None:
        self.samples.append(sample)

    async def list_samples(
        self,
        tenant_id: str,
        limit: int = 100,
        action: str | None = None,
    ) -> list[EvaluationSample]:
        samples = [
            sample
            for sample in self.samples
            if sample.tenant_id == tenant_id and (action is None or sample.action == action)
        ]
        return sorted(samples, key=lambda sample: sample.created_at, reverse=True)[:limit]

    async def summary(self, tenant_id: str) -> dict:
        samples = [sample for sample in self.samples if sample.tenant_id == tenant_id]
        counts = {
            "accept": sum(sample.action == "accept" for sample in samples),
            "edit": sum(sample.action == "edit" for sample in samples),
            "reject": sum(sample.action == "reject" for sample in samples),
        }
        return self._summary(tenant_id, len(samples), counts)

    @staticmethod
    def _summary(tenant_id: str, sample_count: int, counts: dict[str, int]) -> dict:
        denominator = sample_count or 1
        return {
            "tenant_id": tenant_id,
            "sample_count": sample_count,
            "action_counts": counts,
            "acceptance_rate": counts["accept"] / denominator,
            "edit_rate": counts["edit"] / denominator,
            "rejection_rate": counts["reject"] / denominator,
            "draft_useful_rate": (counts["accept"] + counts["edit"]) / denominator,
        }
