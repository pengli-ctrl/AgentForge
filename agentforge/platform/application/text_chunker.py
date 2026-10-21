"""文本分块器模块。"""

from __future__ import annotations


class SimpleTextChunker:
    """简单文本分块器相关组件。"""

    def __init__(self, max_chars: int = 500, overlap: int = 50) -> None:
        """初始化 SimpleTextChunker。

        Args:
            max_chars: 最大。
            overlap: 输入参数。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if max_chars <= 0 or overlap < 0 or overlap >= max_chars:
            raise ValueError("Invalid chunker configuration")
        self._max_chars = max_chars
        self._overlap = overlap

    def split(self, text: str) -> list[str]:
        """按配置参数拆分文本。

        Args:
            text: 待处理文本。

        Returns:
            结果列表。
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
