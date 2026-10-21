"""检索指标模块。"""

from __future__ import annotations


def recall_at_k(
    relevant: set[str],
    retrieved: list[str],
    k: int | None = None,
) -> float:
    """处理召回于K。

    Args:
        relevant: 输入参数。
        retrieved: 已检索。
        k: 返回结果数量上限。

    Returns:
        数值结果。
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
    """处理精确率于K。

    Args:
        relevant: 输入参数。
        retrieved: 已检索。
        k: 返回结果数量上限。

    Returns:
        数值结果。
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
    """处理平均倒数排名。

    Args:
        queries: 输入参数。

    Returns:
        数值结果。
    """
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
    """处理引用准确率。

    Args:
        citations: 引用。
        relevant: 输入参数。

    Returns:
        数值结果。
    """
    if not citations:
        return 0.0
    valid = sum(1 for chunk_id in citations if chunk_id in relevant)
    return valid / len(citations)


def average(values: list[float]) -> float:
    """处理平均。

    Args:
        values: 字段值集合。

    Returns:
        数值结果。
    """
    if not values:
        return 0.0
    return sum(values) / len(values)
