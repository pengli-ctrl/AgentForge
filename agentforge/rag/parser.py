"""解析文档并保留页与坐标。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class DoclingParserAdapter:
    """封装可注入的 Docling 文档解析器。

    The callable receives bytes and metadata and returns a structured document.
    Keeping the callable injectable makes parser upgrades testable without
    requiring Docling/OCR services in unit tests.
    """

    def __init__(self, parse_fn: Callable[[bytes, str, str], dict[str, Any]] | None = None) -> None:
        """解析文档并保留页与坐标。

        Args:
            parse_fn: 调用该函数所需的输入值。
        """
        self._parse_fn = parse_fn

    async def parse(self, content: bytes, *, content_type: str = "", filename: str = "") -> dict[str, Any]:
        """解析文档并保留页与坐标。

        Args:
            content: 调用该函数所需的输入值。
            content_type: 调用该函数所需的输入值。
            filename: 调用该函数所需的输入值。

        Returns:
    当前操作的结构化结果。

        Raises:
    ValueError: 输入不合法时抛出。
        """
        if self._parse_fn is None:
            raise RuntimeError("Docling parser callable is not configured")
        return dict(self._parse_fn(content, content_type, filename))


class FallbackParser:
    """解析文档并保留页与坐标。
    """
    def __init__(self, parsers: list[Any]) -> None:
        """解析文档并保留页与坐标。

        Args:
            parsers: 调用该函数所需的输入值。
        """
        self._parsers = list(parsers)

    async def parse(self, content: bytes, *, content_type: str = "", filename: str = "") -> dict[str, Any]:
        """解析文档并保留页与坐标。

        Args:
            content: 调用该函数所需的输入值。
            content_type: 调用该函数所需的输入值。
            filename: 调用该函数所需的输入值。

        Returns:
    当前操作的结构化结果。

        Raises:
    ValueError: 输入不合法时抛出。
        """
        errors: list[str] = []
        for parser in self._parsers:
            try:
                return await parser.parse(content, content_type=content_type, filename=filename)
            except Exception as exc:
                errors.append(str(exc)[:200])
        raise RuntimeError("all RAG parsers failed: " + "; ".join(errors))


def build_rag_parser(settings: Any, parse_fn=None):
    """解析文档并保留页与坐标。

    Args:
        settings: 调用该函数所需的输入值。
        parse_fn: 调用该函数所需的输入值。

    Raises:
    ValueError: 输入不合法时抛出。
    """
    if settings.rag_parser_backend == "legacy":
        return None
    if settings.rag_parser_backend == "docling":
        return DoclingParserAdapter(parse_fn)
    raise ValueError(f"unsupported rag_parser_backend: {settings.rag_parser_backend}")
