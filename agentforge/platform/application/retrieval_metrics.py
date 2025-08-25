from __future__ import annotations


def recall_at_k(
    relevant: set[str],
    retrieved: list[str],
    k: int | None = None,
) -> float:
    """Recall@K：命中的相关文档数 / 相关文档总数。

    若 relevant 为空视为 0（避免除零，且无相关文档的查询不贡献召回）。
    retrieved 需为按相关性排序的候选 id 列表。
    """
    if not relevant:
        return 0.0
    if k is not None:
        retrieved = retrieved[:k]
    hits = sum(1 for chunk_id in retrieved if chunk_id in relevant)
    return hits / len(relevant)


def precision_at_k(
    relevant: set[str],
    retrieved: list[str],
    k: int | None = None,
) -> float:
    """Precision@K：前 K 个结果中相关文档占比。

    retrieved 为空时返回 0。
    """
    if k is not None:
        retrieved = retrieved[:k]
    if not retrieved:
        return 0.0
    hits = sum(1 for chunk_id in retrieved if chunk_id in relevant)
    return hits / len(retrieved)


def mean_reciprocal_rank(
    queries: list[tuple[set[str], list[str]]],
) -> float:
    """MRR：对所有 (相关集, 排序结果) 计算首个命中位置的倒数取平均。"""
    if not queries:
        return 0.0
    reciprocal_sum = 0.0
    for relevant, retrieved in queries:
        reciprocal = 0.0
        for position, chunk_id in enumerate(retrieved, start=1):
            if chunk_id in relevant:
                reciprocal = 1.0 / position
                break
        reciprocal_sum += reciprocal
    return reciprocal_sum / len(queries)


def citation_accuracy(
    citations: list[str],
    relevant: set[str],
) -> float:
    """引用正确率：草稿引用的 chunk 中有多少属于相关文档集。

    返回 [0, 1]；无引用（空列表）时视为 0，表示该条未给出可验证引用。
    """
    if not citations:
        return 0.0
    valid = sum(1 for chunk_id in citations if chunk_id in relevant)
    return valid / len(citations)


def average(values: list[float]) -> float:
    """列表平均值，空列表返回 0。"""
    if not values:
        return 0.0
    return sum(values) / len(values)
