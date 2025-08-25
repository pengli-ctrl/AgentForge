from __future__ import annotations

import hashlib
import math
from typing import Protocol

# 默认 embedding 维度与版本标识。
# 生产环境可用真实语义模型（如通过 LiteLLM 提供的 embedding）替换默认实现；
# 此处提供确定性的特征哈希向量，保证本地单测、离线回填和 CI 无需外部服务即可运行。
EMBEDDING_DIM = 64
EMBEDDING_MODEL = "agentforge-feature-v1"
EMBEDDING_VERSION = 1


class Embedder(Protocol):
    """把文本编码为定长向量，用于 pgvector / 内存余弦检索。

    实现不要求固定模型，但必须保证：相同输入产生相同向量（确定性），
    以便旧数据可以离线回填 embedding 而不改变索引语义。
    """

    def embed(self, text: str) -> list[float]: ...


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """计算两个向量夹角的余弦相似度，取值范围 [-1, 1]。

    零向量（未归一化或全零）与任意向量的相似度视为 0，避免除零。
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
    """确定性特征哈希向量编码器。

    将文本切分成字符 n-gram（n in 1..3），用 MD5 哈希映射到固定维度桶，
    统计各桶出现次数并做 L2 归一化。共享 n-gram 越多的文本，余弦相似度越高，
    从而让"关键词召回 + 向量召回"有了可验证、可回填的语义基础。
    """

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self._dim = dim

    def embed(self, text: str) -> list[float]:
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
