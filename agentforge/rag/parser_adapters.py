"""文档解析器适配集合。"""
from agentforge.rag.parser import DoclingParserAdapter

class PaddleOcrParserAdapter(DoclingParserAdapter):
    """PaddleOCR 解析适配器。"""

class UnstructuredParserAdapter(DoclingParserAdapter):
    """Unstructured 解析适配器。"""

class TikaParserAdapter(DoclingParserAdapter):
    """Tika 解析适配器。"""
