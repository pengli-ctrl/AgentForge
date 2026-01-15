"""AgentForge 平台应用服务层：retrieval_metrics。

本模块负责 retrieval_metrics 相关的平台能力，是 平台应用服务层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：recall_at_k、precision_at_k、mean_reciprocal_rank、citation_accuracy、average。
"""

from __future__ import annotations


def recall_at_k(
    relevant: set[str],
    retrieved: list[str],
    k: int | None = None,
) -> float:
    """执行 recall_at_k 对应的逻辑，并返回处理结果。

    Args:
        relevant: set[str]，调用方传入的 relevant 参数。
        retrieved: list[str]，调用方传入的 retrieved 参数。
        k: int | None，调用方传入的 k 参数。

    Returns:
        float，函数执行后的结果。
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
    """执行 precision_at_k 对应的逻辑，并返回处理结果。

    Args:
        relevant: set[str]，调用方传入的 relevant 参数。
        retrieved: list[str]，调用方传入的 retrieved 参数。
        k: int | None，调用方传入的 k 参数。

    Returns:
        float，函数执行后的结果。
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
    """执行 mean_reciprocal_rank 对应的逻辑，并返回处理结果。

    Args:
        queries: list[tuple[set[str], list[str]]]，调用方传入的 queries 参数。

    Returns:
        float，函数执行后的结果。
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
    """执行 citation_accuracy 对应的逻辑，并返回处理结果。

    Args:
        citations: list[str]，调用方传入的 citations 参数。
        relevant: set[str]，调用方传入的 relevant 参数。

    Returns:
        float，函数执行后的结果。
    """
    if not citations:
        return 0.0
    valid = sum(1 for chunk_id in citations if chunk_id in relevant)
    return valid / len(citations)


def average(values: list[float]) -> float:
    """执行 average 对应的逻辑，并返回处理结果。

    Args:
        values: list[float]，调用方传入的 values 参数。

    Returns:
        float，函数执行后的结果。
    """
    if not values:
        return 0.0
    return sum(values) / len(values)
