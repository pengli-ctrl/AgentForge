"""混合评分模块。"""

from __future__ import annotations

from agentforge.platform.domain.knowledge import (
    DEFAULT_FTS_WEIGHT,
    DEFAULT_VECTOR_WEIGHT,
    RetrievedChunk,
)

# RRF 融合常数，与 agentforge/rag/hybrid_retriever.py 保持一致。
# 常量：RRF_K。
RRF_K = 60.0


def fuse_scores(
    keyword_scores: dict[str, float],
    vector_scores: dict[str, float],
    fts_weight: float = DEFAULT_FTS_WEIGHT,
    vector_weight: float = DEFAULT_VECTOR_WEIGHT,
) -> dict[str, float]:
    """加权融合关键词分数与向量分数（稠密度量，非 RRF 排名融合）。

    Args:
        keyword_scores: 关键词评分。
        vector_scores: 评分。
        fts_weight: 输入参数。
        vector_weight: 输入参数。

    Returns:
        结构化结果字典。
    """
    all_keys = set(keyword_scores) | set(vector_scores)
    if not all_keys:
        return {}

    def _normalize(scores: dict[str, float]) -> dict[str, float]:
        """规范化数据。

        Args:
            scores: 评分。

        Returns:
            结构化结果字典。
        """
        if not scores:
            return {}
        max_value = max(scores.values())
        if max_value <= 0.0:
            return {key: 0.0 for key in scores}
        return {key: value / max_value for key, value in scores.items()}

    norm_kw = _normalize(keyword_scores)
    norm_vec = _normalize(vector_scores)

    fused: dict[str, float] = {}
    for key in all_keys:
        fused[key] = fts_weight * norm_kw.get(key, 0.0) + vector_weight * norm_vec.get(key, 0.0)
    return fused


def merge_retrieved_chunks(
    chunks_by_id: dict[str, RetrievedChunk],
    fused_scores: dict[str, float],
    mode: str,
) -> list[RetrievedChunk]:
    """合并已检索分片。

    Args:
        chunks_by_id: 分片由 ID。
        fused_scores: 评分。
        mode: 运行模式。

    Returns:
        结果列表。
    """
    results: list[RetrievedChunk] = []
    for chunk_id, score in fused_scores.items():
        chunk = chunks_by_id.get(chunk_id)
        if chunk is None:
            continue
        results.append(
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                tenant_id=chunk.tenant_id,
                title=chunk.title,
                content=chunk.content,
                score=round(float(score), 6),
                source_uri=chunk.source_uri,
                mode=mode,
                fts_score=chunk.fts_score,
                vector_score=chunk.vector_score,
                metadata=dict(chunk.metadata),
            )
        )
    results.sort(key=lambda item: item.score, reverse=True)
    return results
