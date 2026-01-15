"""ASTChunker 单元测试 — AST 代码分块。

测试要点：Python代码解析、函数/类分块、边界处理、嵌套结构。
"""

from __future__ import annotations

from agentforge.rag.ast_chunker import ASTChunker, CodeChunk

SAMPLE_CODE = '''\
"""Module docstring."""

import os
import sys
from typing import Any


def top_level_function(a: int, b: str) -> bool:
    """A top-level function."""
    return True


class MyClass:
    """A sample class."""

    def method_one(self) -> None:
        """First method."""
        pass

    def method_two(self, x: int) -> int:
        """Second method."""
        return x * 2


def another_function():
    """Another top-level function."""
    return None
'''


class TestCodeChunk:
    """CodeChunk 数据类测试。"""

    def test_default_metadata(self) -> None:
        """验证 default_metadata 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        chunk = CodeChunk(content="def foo(): pass")
        assert chunk.content == "def foo(): pass"
        assert chunk.metadata == {}

    def test_with_metadata(self) -> None:
        """验证 with_metadata 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        chunk = CodeChunk(
            content="class Bar: pass",
            metadata={"type": "class", "name": "Bar"},
        )
        assert chunk.metadata["type"] == "class"
        assert chunk.metadata["name"] == "Bar"


class TestASTChunkerInit:
    """初始化测试。"""

    def test_default_language(self) -> None:
        """验证 default_language 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        chunker = ASTChunker()
        assert chunker.language == "python"

    def test_unsupported_language_falls_back(self) -> None:
        """验证 unsupported_language_falls_back 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        chunker = ASTChunker(language="javascript")
        assert chunker.language == "javascript"
        assert chunker._parser is None  # 回退到正则


class TestChunking:
    """代码分块测试。"""

    def test_chunk_returns_list(self) -> None:
        """验证 chunk_returns_list 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        chunker = ASTChunker()
        chunks = chunker.chunk("test.py", SAMPLE_CODE)
        assert isinstance(chunks, list)
        assert len(chunks) > 0

    def test_chunks_contain_content(self) -> None:
        """验证 chunks_contain_content 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        chunker = ASTChunker()
        chunks = chunker.chunk("test.py", SAMPLE_CODE)
        for chunk in chunks:
            assert isinstance(chunk.content, str)
            assert len(chunk.content) > 0

    def test_chunks_have_metadata(self) -> None:
        """验证 chunks_have_metadata 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        chunker = ASTChunker()
        chunks = chunker.chunk("test.py", SAMPLE_CODE)
        for chunk in chunks:
            assert "file_path" in chunk.metadata
            assert chunk.metadata["file_path"] == "test.py"
            assert "type" in chunk.metadata
            assert "name" in chunk.metadata

    def test_top_level_function_detected(self) -> None:
        """验证 top_level_function_detected 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        chunker = ASTChunker()
        chunks = chunker.chunk("test.py", SAMPLE_CODE)
        func_names = [c.metadata["name"] for c in chunks if c.metadata.get("type") == "function"]
        assert "top_level_function" in func_names
        assert "another_function" in func_names

    def test_class_detected(self) -> None:
        """验证 class_detected 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        chunker = ASTChunker()
        chunks = chunker.chunk("test.py", SAMPLE_CODE)
        class_names = [c.metadata["name"] for c in chunks if c.metadata.get("type") == "class"]
        assert "MyClass" in class_names

    def test_methods_detected(self) -> None:
        """验证 methods_detected 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        chunker = ASTChunker()
        chunks = chunker.chunk("test.py", SAMPLE_CODE)
        method_names = [c.metadata["name"] for c in chunks if c.metadata.get("type") == "method"]
        assert "method_one" in method_names
        assert "method_two" in method_names

    def test_class_chunk_includes_method_names(self) -> None:
        """验证 class_chunk_includes_method_names 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        chunker = ASTChunker()
        chunks = chunker.chunk("test.py", SAMPLE_CODE)
        class_chunks = [c for c in chunks if c.metadata.get("type") == "class"]
        assert len(class_chunks) >= 1
        methods = class_chunks[0].metadata.get("methods", [])
        assert "method_one" in methods
        assert "method_two" in methods

    def test_imports_extracted(self) -> None:
        """验证 imports_extracted 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        chunker = ASTChunker()
        chunks = chunker.chunk("test.py", SAMPLE_CODE)
        func_chunks = [c for c in chunks if c.metadata.get("type") == "function"]
        if func_chunks:
            imports = func_chunks[0].metadata.get("imports", [])
            assert any("os" in imp for imp in imports)


class TestEdgeCases:
    """边界处理测试。"""

    def test_empty_code(self) -> None:
        """验证 empty_code 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        chunker = ASTChunker()
        chunks = chunker.chunk("empty.py", "")
        assert chunks == []

    def test_bytes_input(self) -> None:
        """验证 bytes_input 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        chunker = ASTChunker()
        chunks = chunker.chunk("test.py", b"def foo():\n    return 1\n")
        assert len(chunks) >= 1
        assert chunks[0].metadata["name"] == "foo"

    def test_regex_fallback_extracts_functions(self) -> None:
        """验证 regex_fallback_extracts_functions 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        chunker = ASTChunker(language="unknown")
        # 降级处理。
        assert chunker._parser is None
        code = "def alpha():\n    pass\n\ndef beta():\n    return 1\n"
        chunks = chunker.chunk("test.py", code)
        names = [c.metadata["name"] for c in chunks]
        assert "alpha" in names
        assert "beta" in names
