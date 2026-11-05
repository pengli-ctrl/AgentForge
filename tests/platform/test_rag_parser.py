import pytest

from agentforge.platform.settings import Settings
from agentforge.rag.parser import DoclingParserAdapter, FallbackParser, build_rag_parser


@pytest.mark.asyncio
async def test_docling_adapter_preserves_page_and_bbox() -> None:
    def parse(content, content_type, filename):
        return {"page": 3, "bbox": [1, 2, 3, 4], "text": content.decode(), "filename": filename}
    adapter = DoclingParserAdapter(parse)
    result = await adapter.parse(b"hello", filename="a.pdf")
    assert result["page"] == 3
    assert result["bbox"] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_fallback_parser_uses_next_parser() -> None:
    class Bad:
        async def parse(self, *args, **kwargs): raise RuntimeError("bad")
    class Good:
        async def parse(self, *args, **kwargs): return {"text": "ok"}
    result = await FallbackParser([Bad(), Good()]).parse(b"x")
    assert result["text"] == "ok"


def test_rag_parser_factory_defaults_to_legacy() -> None:
    assert build_rag_parser(Settings(_env_file=None)) is None
