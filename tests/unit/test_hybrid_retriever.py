"""混合检索测试 — RRF 融合逻辑。

测试内容：
- RRF 融合公式正确性
- 单路检索（仅 BM25 / 仅 FAISS）
- 双路检索 + RRF 融合
- 融合结果排序正确性
"""

from __future__ import annotations

import numpy as np

from agentforge.rag.hybrid_retriever import RRF_K, HybridRetriever


class MockBM25Index:
    """Mock BM25 索引。"""

    def __init__(self, scores: np.ndarray) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            scores: np.ndarray，调用方传入的 scores 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._scores = scores

    def get_scores(self, query: str) -> np.ndarray:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            query: str，调用方传入的 query 参数。

        Returns:
            np.ndarray，函数执行后的结果。
        """
        return self._scores


class MockFAISSIndex:
    """MockFAISSIndex。

    MockFAISSIndex 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 search()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(self, indices: np.ndarray) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            indices: np.ndarray，调用方传入的 indices 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._indices = indices

    def search(self, embeddings: np.ndarray, k: int) -> tuple:
        """执行 search 对应的核心操作，并保持调用契约稳定。

        Args:
            embeddings: np.ndarray，调用方传入的 embeddings 参数。
            k: int，调用方传入的 k 参数。

        Returns:
            tuple，函数执行后的结果。
        """
        return np.array([[0.0] * k]), self._indices[:k].reshape(1, -1)


class MockEmbedModel:
    """Mock 向量编码模型。"""

    def encode(self, texts: list[str]) -> np.ndarray:
        """执行 encode 对应的逻辑，并返回处理结果。

        Args:
            texts: list[str]，调用方传入的 texts 参数。

        Returns:
            np.ndarray，函数执行后的结果。
        """
        return np.array([[0.1] * 128])


class TestRRFFusion:
    """RRF 融合逻辑测试。"""

    def test_rrf_fuse_both_paths(self) -> None:
        """双路检索 RRF 融合 — 两路都有结果。"""
        retriever = HybridRetriever(top_k=5)

        bm25_rank = {0: 0, 1: 1, 2: 2}  # doc 0 排第1, doc 1 排第2, doc 2 排第3
        faiss_rank = {1: 0, 3: 1, 0: 2}  # doc 1 排第1, doc 3 排第2, doc 0 排第3

        fused = retriever._rrf_fuse(bm25_rank, faiss_rank)

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。

        expected_0 = 1.0 / (RRF_K + 0) + 1.0 / (RRF_K + 2)
        expected_1 = 1.0 / (RRF_K + 1) + 1.0 / (RRF_K + 0)
        expected_2 = 1.0 / (RRF_K + 2)
        expected_3 = 1.0 / (RRF_K + 1)

        assert abs(fused[0] - expected_0) < 1e-10
        assert abs(fused[1] - expected_1) < 1e-10
        assert abs(fused[2] - expected_2) < 1e-10
        assert abs(fused[3] - expected_3) < 1e-10

        # doc 1 应该排第一（在两路中都排名靠前）
        sorted_docs = sorted(fused.keys(), key=lambda x: fused[x], reverse=True)
        assert sorted_docs[0] == 1  # doc 1 融合分数最高

    def test_rrf_fuse_bm25_only(self) -> None:
        """仅 BM25 路有结果。"""
        retriever = HybridRetriever(top_k=5)

        bm25_rank = {0: 0, 1: 1, 2: 2}
        faiss_rank: dict[int, int] = {}

        fused = retriever._rrf_fuse(bm25_rank, faiss_rank)

        # 只有 BM25 分数
        assert abs(fused[0] - 1.0 / (RRF_K + 0)) < 1e-10
        assert abs(fused[1] - 1.0 / (RRF_K + 1)) < 1e-10
        assert abs(fused[2] - 1.0 / (RRF_K + 2)) < 1e-10

    def test_rrf_fuse_faiss_only(self) -> None:
        """仅 FAISS 路有结果。"""
        retriever = HybridRetriever(top_k=5)

        bm25_rank: dict[int, int] = {}
        faiss_rank = {0: 0, 1: 1, 2: 2}

        fused = retriever._rrf_fuse(bm25_rank, faiss_rank)

        assert abs(fused[0] - 1.0 / (RRF_K + 0)) < 1e-10
        assert abs(fused[1] - 1.0 / (RRF_K + 1)) < 1e-10

    def test_rrf_fuse_empty(self) -> None:
        """两路都无结果。"""
        retriever = HybridRetriever(top_k=5)

        fused = retriever._rrf_fuse({}, {})

        assert len(fused) == 0

    def test_rrf_fuse_disjoint_sets(self) -> None:
        """两路结果完全不重叠。"""
        retriever = HybridRetriever(top_k=5)

        bm25_rank = {0: 0, 1: 1}
        faiss_rank = {2: 0, 3: 1}

        fused = retriever._rrf_fuse(bm25_rank, faiss_rank)

        # 4 个文档都应出现在融合结果中
        assert len(fused) == 4
        assert 0 in fused
        assert 1 in fused
        assert 2 in fused
        assert 3 in fused

        # 两路各排第一的文档分数应相同
        assert abs(fused[0] - fused[2]) < 1e-10
        assert abs(fused[1] - fused[3]) < 1e-10


class TestHybridRetrieverSearch:
    """混合检索器搜索测试。"""

    def test_search_with_mock_indices(self) -> None:
        """使用 Mock 索引测试搜索。"""
        bm25 = MockBM25Index(np.array([0.1, 0.5, 0.3, 0.8, 0.2]))
        faiss = MockFAISSIndex(np.array([3, 1, 0, 4, 2]))
        embed = MockEmbedModel()

        retriever = HybridRetriever(
            bm25_index=bm25,
            faiss_index=faiss,
            embed_model=embed,
            top_k=3,
        )

        results = retriever.search("test query")

        # 应返回 top_k 个结果
        assert len(results) <= 3
        assert len(results) > 0

    def test_search_no_indices(self) -> None:
        """无索引时搜索返回空列表。"""
        retriever = HybridRetriever(
            bm25_index=None,
            faiss_index=None,
            embed_model=None,
            top_k=5,
        )

        results = retriever.search("test query")

        assert results == []

    def test_search_bm25_only(self) -> None:
        """仅 BM25 索引搜索。"""
        bm25 = MockBM25Index(np.array([0.1, 0.5, 0.3, 0.8, 0.2]))

        retriever = HybridRetriever(
            bm25_index=bm25,
            faiss_index=None,
            embed_model=None,
            top_k=3,
        )

        results = retriever.search("test query")

        # BM25 分数最高的排前面: 0.8 > 0.5 > 0.3 > 0.2 > 0.1
        # 索引 3 分数最高
        assert 3 in results
        assert results[0] == 3  # doc 3 分数最高

    def test_search_top_k_limit(self) -> None:
        """搜索结果不超过 top_k。"""
        bm25 = MockBM25Index(np.array([0.1, 0.5, 0.3, 0.8, 0.2, 0.9, 0.4]))

        retriever = HybridRetriever(
            bm25_index=bm25,
            faiss_index=None,
            embed_model=None,
            top_k=3,
        )

        results = retriever.search("test query")

        assert len(results) <= 3
