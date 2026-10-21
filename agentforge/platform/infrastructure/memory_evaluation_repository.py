"""记忆评估仓储模块。"""

from __future__ import annotations

from agentforge.platform.domain.evaluation import EvaluationSample


class MemoryEvaluationRepository:
    """评估仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryEvaluationRepository。"""
        self.samples: list[EvaluationSample] = []

    async def save(self, sample: EvaluationSample) -> None:
        """保存评估。

        Args:
            sample: 评估样本。
        """
        self.samples.append(sample)

    async def list_samples(
        self,
        tenant_id: str,
        limit: int = 100,
        action: str | None = None,
    ) -> list[EvaluationSample]:
        """查询样本。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。
            action: 待执行动作名称。

        Returns:
            结果列表。
        """
        samples = [
            sample
            for sample in self.samples
            if sample.tenant_id == tenant_id and (action is None or sample.action == action)
        ]
        return sorted(samples, key=lambda sample: sample.created_at, reverse=True)[:limit]

    async def summary(self, tenant_id: str) -> dict:
        """处理摘要。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        samples = [sample for sample in self.samples if sample.tenant_id == tenant_id]
        counts = {
            "accept": sum(sample.action == "accept" for sample in samples),
            "edit": sum(sample.action == "edit" for sample in samples),
            "reject": sum(sample.action == "reject" for sample in samples),
        }
        return self._summary(tenant_id, len(samples), counts)

    @staticmethod
    def _summary(tenant_id: str, sample_count: int, counts: dict[str, int]) -> dict:
        """处理摘要。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            sample_count: 样本数量。
            counts: 输入参数。

        Returns:
            结构化结果字典。
        """
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
