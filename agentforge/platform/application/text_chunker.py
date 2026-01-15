"""AgentForge 平台应用服务层：text_chunker。

本模块负责 text_chunker 相关的平台能力，是 平台应用服务层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：SimpleTextChunker。
"""

from __future__ import annotations


class SimpleTextChunker:
    """SimpleTextChunker。

    SimpleTextChunker 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 split()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, max_chars: int = 500, overlap: int = 50) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            max_chars: int，调用方传入的 max_chars 参数。
            overlap: int，调用方传入的 overlap 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if max_chars <= 0 or overlap < 0 or overlap >= max_chars:
            raise ValueError("Invalid chunker configuration")
        self._max_chars = max_chars
        self._overlap = overlap

    def split(self, text: str) -> list[str]:
        """执行 split 对应的逻辑，并返回处理结果。

        Args:
            text: str，调用方传入的 text 参数。

        Returns:
            list[str]，函数执行后的结果。
        """
        normalized = text.strip()
        if not normalized:
            return []
        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(start + self._max_chars, len(normalized))
            chunk = normalized[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end == len(normalized):
                break
            start = end - self._overlap
        return chunks
