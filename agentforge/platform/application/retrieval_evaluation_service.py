"""AgentForge 平台应用服务层：retrieval_evaluation_service。

本模块实现 retrieval_evaluation_service 应用服务，编排多个领域对象和基础设施组件完成业务流程。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：RetrievalEvaluationService。
"""

from __future__ import annotations

from agentforge.platform.application.ports import KnowledgeRepository
from agentforge.platform.application.reranker import Reranker
from agentforge.platform.application.retrieval_metrics import (
    average,
    citation_accuracy,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)
from agentforge.platform.domain.knowledge import SearchMode
from agentforge.platform.domain.retrieval import (
    GoldenQuery,
    QueryEvaluation,
    RetrievalReport,
)


class RetrievalEvaluationService:
    """RetrievalEvaluationService。

    RetrievalEvaluationService 编排业务流程，协调仓储、模型、策略和外部连接器完成用例。

    主要成员：
    - 方法 evaluate()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        repository: KnowledgeRepository,
        reranker: Reranker | None = None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            repository: KnowledgeRepository，调用方传入的 repository 参数。
            reranker: Reranker | None，调用方传入的 reranker 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._repository = repository
        self._reranker = reranker

    async def evaluate(
        self,
        queries: list[GoldenQuery],
        k: int = 5,
        rerank: bool = True,
        mode: SearchMode = "hybrid",
    ) -> RetrievalReport:
        """执行 evaluate 对应的逻辑，并返回处理结果。

        Args:
            queries: list[GoldenQuery]，调用方传入的 queries 参数。
            k: int，调用方传入的 k 参数。
            rerank: bool，调用方传入的 rerank 参数。
            mode: SearchMode，调用方传入的 mode 参数。

        Returns:
            RetrievalReport，函数执行后的结果。
        """
        evaluations: list[QueryEvaluation] = []
        for golden in queries:
            results = await self._repository.search(
                golden.tenant_id,
                golden.query,
                limit=k,
                mode=mode,
            )
            if rerank and self._reranker is not None:
                results = self._reranker.rerank(golden.query, results)

            relevant = set(golden.expected_chunk_ids)
            retrieved_ids = [chunk.chunk_id for chunk in results]
            reciprocal = 0.0
            for position, chunk_id in enumerate(retrieved_ids, start=1):
                if chunk_id in relevant:
                    reciprocal = 1.0 / position
                    break
            evaluations.append(
                QueryEvaluation(
                    query=golden.query,
                    retrieved=retrieved_ids,
                    retrieved_chunks=results,
                    recall_at_k=recall_at_k(relevant, retrieved_ids, k),
                    precision_at_k=precision_at_k(relevant, retrieved_ids, k),
                    reciprocal_rank=reciprocal,
                    citation_accuracy=citation_accuracy(golden.expected_citations, relevant),
                )
            )

        pairs = [
            (set(q.expected_chunk_ids), [c.chunk_id for c in e.retrieved_chunks])
            for q, e in zip(queries, evaluations)
        ]
        per_query_citations = [e.citation_accuracy for e in evaluations]
        return RetrievalReport(
            query_count=len(queries),
            recall_at_k=average([e.recall_at_k for e in evaluations]),
            precision_at_k=average([e.precision_at_k for e in evaluations]),
            mean_reciprocal_rank=mean_reciprocal_rank(pairs),
            citation_accuracy=average(per_query_citations),
            k=k,
            per_query=evaluations,
        )
