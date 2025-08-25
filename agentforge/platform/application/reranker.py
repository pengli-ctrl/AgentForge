from __future__ import annotations

import re
from typing import Protocol

from agentforge.platform.domain.knowledge import (
    RetrievedChunk,
)


class Reranker(Protocol):
    """对检索结果做二次排序（重排）。

    接收原始检索候选（已带 fts_score / vector_score），结合查询与文档内容
    重新计算排序分并返回重排后的候选列表。实现须是确定性、可离线运行，
    便于单元测试与召回评估。
    """

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]: ...


def _tokenize(text: str) -> list[str]:
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
        self._fts_weight = fts_weight
        self._vector_weight = vector_weight

    def _base_score(self, chunk: RetrievedChunk) -> float:
        fts = chunk.fts_score or 0.0
        vector = chunk.vector_score or 0.0
        return self._fts_weight * fts + self._vector_weight * vector

    def _coverage_score(self, query_tokens: list[str], chunk: RetrievedChunk) -> float:
        if not query_tokens:
            return 0.0
        haystack = f"{chunk.title} {chunk.content}".lower()
        return sum(1.0 for token in query_tokens if token in haystack) / len(query_tokens)

    def _position_score(self, query_tokens: list[str], chunk: RetrievedChunk) -> float:
        """标题命中给最高分；正文命中越靠前分越高。"""
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
