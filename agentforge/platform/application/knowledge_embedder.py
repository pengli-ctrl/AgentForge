"""AgentForge 平台应用服务层：knowledge_embedder。

本模块负责 knowledge_embedder 相关的平台能力，是 平台应用服务层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：Embedder、HashEmbedder。
- 主要函数：cosine_similarity。
"""

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
    """Embedder。

    Embedder 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 embed()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def embed(self, text: str) -> list[float]:
        """执行 embed 对应的逻辑，并返回处理结果。

        Args:
            text: str，调用方传入的 text 参数。

        Returns:
            list[float]，函数执行后的结果。
        """
        ...


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """执行 cosine_similarity 对应的逻辑，并返回处理结果。

    Args:
        left: list[float]，调用方传入的 left 参数。
        right: list[float]，调用方传入的 right 参数。

    Returns:
        float，函数执行后的结果。
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
    """HashEmbedder。

    HashEmbedder 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 embed()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            dim: int，调用方传入的 dim 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if dim <= 0:
            raise ValueError("dim must be positive")
        self._dim = dim

    def embed(self, text: str) -> list[float]:
        """执行 embed 对应的逻辑，并返回处理结果。

        Args:
            text: str，调用方传入的 text 参数。

        Returns:
            list[float]，函数执行后的结果。
        """
        vector = [0.0] * self._dim
        normalized = (text or "").lower()
        for gram_size in (1, 2, 3):
            if len(normalized) < gram_size:
                continue
            for start in range(len(normalized) - gram_size + 1):
                gram = normalized[start : start + gram_size]
                digest = hashlib.md5(gram.encode("utf-8")).digest()
                bucket = int.from_bytes(digest[:4], "big") % self._dim
                vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]
