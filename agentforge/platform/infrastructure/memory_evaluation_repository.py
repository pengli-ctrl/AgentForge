"""AgentForge 平台基础设施层：memory_evaluation_repository。

本模块提供 memory_evaluation_repository 的内存实现，用于单元测试、本地开发和离线验证。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：MemoryEvaluationRepository。
"""

from __future__ import annotations

from agentforge.platform.domain.evaluation import EvaluationSample


class MemoryEvaluationRepository:
    """MemoryEvaluationRepository。

    MemoryEvaluationRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 save()。
    - 方法 list_samples()。
    - 方法 summary()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self.samples: list[EvaluationSample] = []

    async def save(self, sample: EvaluationSample) -> None:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            sample: EvaluationSample，调用方传入的 sample 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.samples.append(sample)

    async def list_samples(
        self,
        tenant_id: str,
        limit: int = 100,
        action: str | None = None,
    ) -> list[EvaluationSample]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。
            action: str | None，调用方传入的 action 参数。

        Returns:
            list[EvaluationSample]，函数执行后的结果。
        """
        samples = [
            sample
            for sample in self.samples
            if sample.tenant_id == tenant_id and (action is None or sample.action == action)
        ]
        return sorted(samples, key=lambda sample: sample.created_at, reverse=True)[:limit]

    async def summary(self, tenant_id: str) -> dict:
        """执行 summary 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。
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
        """执行 _summary 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            sample_count: int，调用方传入的 sample_count 参数。
            counts: dict[str, int]，调用方传入的 counts 参数。

        Returns:
            dict，函数执行后的结果。
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
