"""测试可插拔 RAG 解析器。"""

import pytest

from agentforge.platform.settings import Settings
from agentforge.rag.parser import DoclingParserAdapter, FallbackParser, build_rag_parser


class BadParser:
    """提供失败解析器。"""

    async def parse(self, *args, **kwargs):
        """抛出解析错误。

        Args:
            *args: 位置参数。
            **kwargs: 关键字参数。

        Raises:
            RuntimeError: 固定失败。
        """
        raise RuntimeError("bad")


class GoodParser:
    """提供成功解析器。"""

    async def parse(self, *args, **kwargs):
        """返回固定结果。

        Args:
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            固定结果。
        """
        return {"text": "ok"}


@pytest.mark.asyncio
async def test_docling_adapter_preserves_page_and_bbox() -> None:
    """验证 Docling 适配保留页码和坐标。"""

    def parse(content, content_type, filename):
        """返回解析结果。

        Args:
            content: 文件内容。
            content_type: 文件类型。
            filename: 文件名。

        Returns:
            解析结果。
        """
        return {"page": 3, "bbox": [1, 2, 3, 4], "text": content.decode(), "filename": filename}

    adapter = DoclingParserAdapter(parse)
    result = await adapter.parse(b"hello", filename="a.pdf")
    assert result["page"] == 3
    assert result["bbox"] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_fallback_parser_uses_next_parser() -> None:
    """验证失败后切换解析器。"""
    result = await FallbackParser([BadParser(), GoodParser()]).parse(b"x")
    assert result["text"] == "ok"


def test_rag_parser_factory_defaults_to_legacy() -> None:
    """验证默认使用旧解析器。"""
    assert build_rag_parser(Settings(_env_file=None)) is None
