"""测试 RAG 解析器适配集合。"""
from agentforge.rag.parser_adapters import PaddleOcrParserAdapter, TikaParserAdapter, UnstructuredParserAdapter

def test_parser_adapters_are_constructible():
    """验证解析适配器可构造。"""
    fn = lambda content, content_type, filename: {"text": "ok"}
    assert PaddleOcrParserAdapter(fn)
    assert UnstructuredParserAdapter(fn)
    assert TikaParserAdapter(fn)