"""测试 RAG 解析器适配集合。"""

from unittest.mock import Mock

from agentforge.rag.parser_adapters import (
    PaddleOcrParserAdapter,
    TikaParserAdapter,
    UnstructuredParserAdapter,
)


def test_parser_adapters_are_constructible():
    """验证解析适配器可构造。"""
    fn = Mock(return_value={"text": "ok"})
    assert PaddleOcrParserAdapter(fn)
    assert UnstructuredParserAdapter(fn)
    assert TikaParserAdapter(fn)
