"""重排器模块。"""

from __future__ import annotations

import re
from typing import Protocol

from agentforge.platform.domain.knowledge import RetrievedChunk


class Reranker(Protocol):
    """重排器相关组件。"""

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """重排器。

        Args:
            query: 检索或筛选查询。
            candidates: 输入参数。

        Returns:
            结果列表。
        """
        ...


def _tokenize(text: str) -> list[str]:
    """处理分词。

    Args:
        text: 待处理文本。

    Returns:
        结果列表。
    """
    return [token.lower() for token in re.findall(r"[a-zA-Z0-9]+", text or "")]


class HybridReranker:
    """基于检索分 + 查询词覆盖度的确定性重排器。"""

    def __init__(self, fts_weight: float = 0.5, vector_weight: float = 0.5) -> None:
        """初始化 HybridReranker。

        Args:
            fts_weight: 输入参数。
            vector_weight: 输入参数。
        """
        self._fts_weight = fts_weight
        self._vector_weight = vector_weight

    def _base_score(self, chunk: RetrievedChunk) -> float:
        """处理基础评分。

        Args:
            chunk: 分块。

        Returns:
            数值结果。
        """
        fts = chunk.fts_score or 0.0
        vector = chunk.vector_score or 0.0
        return self._fts_weight * fts + self._vector_weight * vector

    def _coverage_score(self, query_tokens: list[str], chunk: RetrievedChunk) -> float:
        """处理覆盖率评分。

        Args:
            query_tokens: 查询。
            chunk: 分块。

        Returns:
            数值结果。
        """
        if not query_tokens:
            return 0.0
        haystack = f"{chunk.title} {chunk.content}".lower()
        return sum(1.0 for token in query_tokens if token in haystack) / len(query_tokens)

    def _position_score(self, query_tokens: list[str], chunk: RetrievedChunk) -> float:
        """处理位置评分。

        Args:
            query_tokens: 查询。
            chunk: 分块。

        Returns:
            数值结果。
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
        """重排混合重排器。

        Args:
            query: 检索或筛选查询。
            candidates: 输入参数。

        Returns:
            结果列表。
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
