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
    """离线检索与引用质量评估服务。

    对每条 GoldenQuery 依次执行：混合检索 -> 可选重排 -> 计算 Recall@K /
    Precision@K / 倒数排名 / 引用正确率，最后聚合为整体报告。
    评估为在线计算，不落库；如需持久化回归结果，可在此基础上扩展仓储。
    """

    def __init__(
        self,
        repository: KnowledgeRepository,
        reranker: Reranker | None = None,
    ) -> None:
        self._repository = repository
        self._reranker = reranker

    async def evaluate(
        self,
        queries: list[GoldenQuery],
        k: int = 5,
        rerank: bool = True,
        mode: SearchMode = "hybrid",
    ) -> RetrievalReport:
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
