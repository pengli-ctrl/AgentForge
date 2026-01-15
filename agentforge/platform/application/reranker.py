"""AgentForge 平台应用服务层：reranker。

本模块负责 reranker 相关的平台能力，是 平台应用服务层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：Reranker、HybridReranker。
"""

from __future__ import annotations

import re
from typing import Protocol

from agentforge.platform.domain.knowledge import (
    RetrievedChunk,
)


class Reranker(Protocol):
    """Reranker。

    Reranker 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 rerank()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """执行 rerank 对应的逻辑，并返回处理结果。

        Args:
            query: str，调用方传入的 query 参数。
            candidates: list[RetrievedChunk]，调用方传入的 candidates 参数。

        Returns:
            list[RetrievedChunk]，函数执行后的结果。
        """
        ...


def _tokenize(text: str) -> list[str]:
    """执行 _tokenize 对应的逻辑，并返回处理结果。

    Args:
        text: str，调用方传入的 text 参数。

    Returns:
        list[str]，函数执行后的结果。
    """
    return [token.lower() for token in re.findall(r"[a-zA-Z0-9]+", text or "")]


class HybridReranker:
    """基于检索分 + 查询词覆盖度的确定性重排器。

    排序分由三部分合成：
        1. 基础检索分 base = fts_weight * fts + vector_weight * vector
        2. 查询词覆盖加成 coverage = 查询 token 中出现在 title/content 的比例
        3. 命中位置加成：查询词出现越靠前权重越高（title 命中 > content 靠前命中）

    所有部分均为确定性计算，便于测试、离线评估与生产热替换。
    """

    def __init__(self, fts_weight: float = 0.5, vector_weight: float = 0.5) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            fts_weight: float，调用方传入的 fts_weight 参数。
            vector_weight: float，调用方传入的 vector_weight 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._fts_weight = fts_weight
        self._vector_weight = vector_weight

    def _base_score(self, chunk: RetrievedChunk) -> float:
        """执行 _base_score 对应的逻辑，并返回处理结果。

        Args:
            chunk: RetrievedChunk，调用方传入的 chunk 参数。

        Returns:
            float，函数执行后的结果。
        """
        fts = chunk.fts_score or 0.0
        vector = chunk.vector_score or 0.0
        return self._fts_weight * fts + self._vector_weight * vector

    def _coverage_score(self, query_tokens: list[str], chunk: RetrievedChunk) -> float:
        """执行 _coverage_score 对应的逻辑，并返回处理结果。

        Args:
            query_tokens: list[str]，调用方传入的 query_tokens 参数。
            chunk: RetrievedChunk，调用方传入的 chunk 参数。

        Returns:
            float，函数执行后的结果。
        """
        if not query_tokens:
            return 0.0
        haystack = f"{chunk.title} {chunk.content}".lower()
        return sum(1.0 for token in query_tokens if token in haystack) / len(query_tokens)

    def _position_score(self, query_tokens: list[str], chunk: RetrievedChunk) -> float:
        """执行 _position_score 对应的逻辑，并返回处理结果。

        Args:
            query_tokens: list[str]，调用方传入的 query_tokens 参数。
            chunk: RetrievedChunk，调用方传入的 chunk 参数。

        Returns:
            float，函数执行后的结果。
        """
        if not query_tokens:
            return 0.0
        score = 0.0
        for token in query_tokens:
            title_pos = (chunk.title or "").lower().find(token)
            if title_pos >= 0:
                score += 1.0
                continue
            content_pos = (chunk.content or "").lower().find(token)
            if content_pos >= 0:
                score += max(0.0, 1.0 - content_pos / max(1.0, len(chunk.content or "")))
        return score / len(query_tokens)

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """执行 rerank 对应的逻辑，并返回处理结果。

        Args:
            query: str，调用方传入的 query 参数。
            candidates: list[RetrievedChunk]，调用方传入的 candidates 参数。

        Returns:
            list[RetrievedChunk]，函数执行后的结果。
        """
        query_tokens = _tokenize(query)
        scored: list[tuple[float, RetrievedChunk]] = []
        for chunk in candidates:
            total = (
                self._base_score(chunk)
                + self._coverage_score(query_tokens, chunk)
                + self._position_score(query_tokens, chunk)
            )
            scored.append((total, chunk))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [chunk for _, chunk in scored]
