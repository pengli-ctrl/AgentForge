"""混合模块。"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# RRF 常数
RRF_K = 60


class HybridRetriever:
    """混合相关组件。"""

    def __init__(
        self,
        bm25_index: Any = None,
        faiss_index: Any = None,
        embed_model: Any = None,
        top_k: int = 20,
    ) -> None:
        """初始化 HybridRetriever。

        Args:
            bm25_index: 索引。
            faiss_index: 索引。
            embed_model: 向量化模型。
            top_k: 返回结果数量上限。
        """
        self.bm25_index = bm25_index
        self.faiss_index = faiss_index
        self.embed_model = embed_model
        self.top_k = top_k

    def search(self, query: str, top_k: int | None = None) -> list[int]:
        """搜索与查询条件匹配的数据。

        Args:
            query: 检索或筛选查询。
            top_k: 返回结果数量上限。

        Returns:
            结果列表。
        """
        k = top_k or self.top_k

        # 路 1: BM25 关键词检索
        bm25_rank = self._bm25_search(query, k * 2)

        # 路 2: FAISS 向量检索
        faiss_rank = self._faiss_search(query, k * 2)

        # RRF 融合
        fused_scores = self._rrf_fuse(bm25_rank, faiss_rank)

        # 按融合分数排序
        sorted_indices = sorted(
            fused_scores.keys(),
            key=lambda x: fused_scores[x],
            reverse=True,
        )

        logger.info(
            "Hybrid search completed (query='%s', bm25_results=%d, "
            "faiss_results=%d, fused=%d, returning=%d)",
            query[:50],
            len(bm25_rank),
            len(faiss_rank),
            len(fused_scores),
            min(k, len(sorted_indices)),
        )

        return sorted_indices[:k]

    def _bm25_search(self, query: str, top_n: int) -> dict[int, int]:
        """BM25 关键词检索。

        Args:
            query: 检索或筛选查询。
            top_n: 输入参数。

        Returns:
            结构化结果字典。
        """
        if self.bm25_index is None:
            return {}

        bm25_scores = self.bm25_index.get_scores(query)
        bm25_top_indices = np.argsort(bm25_scores)[::-1][:top_n]
        return {int(idx): rank for rank, idx in enumerate(bm25_top_indices)}

    def _faiss_search(self, query: str, top_n: int) -> dict[int, int]:
        """处理搜索。

        Args:
            query: 检索或筛选查询。
            top_n: 输入参数。

        Returns:
            结构化结果字典。
        """
        if self.faiss_index is None or self.embed_model is None:
            return {}

        query_embedding = self.embed_model.encode([query])
        _, faiss_top_indices = self.faiss_index.search(query_embedding, top_n)
        return {int(idx): rank for rank, idx in enumerate(faiss_top_indices[0])}

    def _rrf_fuse(
        self,
        bm25_rank: dict[int, int],
        faiss_rank: dict[int, int],
    ) -> dict[int, float]:
        """处理倒数排名融合。

        Args:
            bm25_rank: 排名。
            faiss_rank: 排名。

        Returns:
            结构化结果字典。
        """
        fused_scores: dict[int, float] = {}
        all_indices = set(bm25_rank.keys()) | set(faiss_rank.keys())

        for idx in all_indices:
            score = 0.0
            if idx in bm25_rank:
                score += 1.0 / (RRF_K + bm25_rank[idx])
            if idx in faiss_rank:
                score += 1.0 / (RRF_K + faiss_rank[idx])
            fused_scores[idx] = score

        return fused_scores
