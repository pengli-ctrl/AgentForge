"""提供架构升级适配。"""

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
        """提供架构升级适配。

        Args:
            parse_fn: 输入参数。
        """
        self._parse_fn = parse_fn

    async def parse(self, content: bytes, *, content_type: str = "", filename: str = "") -> dict[str, Any]:
        """提供架构升级适配。

        Args:
            content: 输入参数。
            content_type: 输入参数。
            filename: 输入参数。

        Returns:
    处理结果。

        Raises:
    ValueError: 输入不合法时抛出。
        """
        if self._parse_fn is None:
            raise RuntimeError("Docling parser callable is not configured")
        return dict(self._parse_fn(content, content_type, filename))


class FallbackParser:
    """提供架构升级适配。
    """
    def __init__(self, parsers: list[Any]) -> None:
        """提供架构升级适配。

        Args:
            parsers: 输入参数。
        """
        self._parsers = list(parsers)

    async def parse(self, content: bytes, *, content_type: str = "", filename: str = "") -> dict[str, Any]:
        """提供架构升级适配。

        Args:
            content: 输入参数。
            content_type: 输入参数。
            filename: 输入参数。

        Returns:
    处理结果。

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
    """提供架构升级适配。

    Args:
        settings: 输入参数。
        parse_fn: 输入参数。

    Raises:
    ValueError: 输入不合法时抛出。
    """
    if settings.rag_parser_backend == "legacy":
        return None
    if settings.rag_parser_backend == "docling":
        return DoclingParserAdapter(parse_fn)
    raise ValueError(f"unsupported rag_parser_backend: {settings.rag_parser_backend}")
