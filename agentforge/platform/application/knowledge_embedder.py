"""知识向量化器模块。"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

# 默认 embedding 维度与版本标识。
# 生产环境可用真实语义模型（如通过 LiteLLM 提供的 embedding）替换默认实现；
# 此处提供确定性的特征哈希向量，保证本地单测、离线回填和 CI 无需外部服务即可运行。
# 常量：EMBEDDING_DIM。
EMBEDDING_DIM = 64
# 常量：EMBEDDING_MODEL。
EMBEDDING_MODEL = "agentforge-feature-v1"
# 常量：EMBEDDING_VERSION。
EMBEDDING_VERSION = 1


class Embedder(Protocol):
    """向量化器相关组件。"""

    def embed(self, text: str) -> list[float]:
        """向量化器。

        Args:
            text: 待处理文本。

        Returns:
            结果列表。
        """
        ...


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """计算两个向量的余弦相似度。

    Args:
        left: 输入参数。
        right: 输入参数。

    Returns:
        数值结果。
    """
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    norm_left = 0.0
    norm_right = 0.0
    for a, b in zip(left, right):
        dot += a * b
        norm_left += a * a
        norm_right += b * b
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_left) * math.sqrt(norm_right))


class HashEmbedder:
    """哈希向量化器相关组件。"""

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        """初始化 HashEmbedder。

        Args:
            dim: 输入参数。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if dim <= 0:
            raise ValueError("dim must be positive")
        self._dim = dim

    def embed(self, text: str) -> list[float]:
        """向量化哈希向量化器。

        Args:
            text: 待处理文本。

        Returns:
            结果列表。
        """
        vector = [0.0] * self._dim
        normalized = (text or "").lower()
        for gram_size in (1, 2, 3):
            if len(normalized) < gram_size:
                continue
            for start in range(len(normalized) - gram_size + 1):
                gram = normalized[start : start + gram_size]
                digest = hashlib.md5(gram.encode("utf-8"), usedforsecurity=False).digest()
                bucket = int.from_bytes(digest[:4], "big") % self._dim
                vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]
