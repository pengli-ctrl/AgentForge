from __future__ import annotations


class SimpleTextChunker:
    def __init__(self, max_chars: int = 500, overlap: int = 50) -> None:
        if max_chars <= 0 or overlap < 0 or overlap >= max_chars:
            raise ValueError("Invalid chunker configuration")
        self._max_chars = max_chars
        self._overlap = overlap

    def split(self, text: str) -> list[str]:
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
