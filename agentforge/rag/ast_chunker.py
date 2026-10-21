"""AST分块器模块。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CodeChunk:
    """代码分块 — 一个完整的语法单元。

    Attributes:
        content: 写入内容。
        metadata: 附加元数据。
    """

    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ASTChunker:
    """AST 感知的代码分块器 — 按函数/类/方法级别切分代码。"""

    def __init__(self, language: str = "python") -> None:
        """初始化 ASTChunker。

        Args:
            language: 语言。
        """
        self.language = language
        self._parser: Any | None = None
        self._init_parser()

    def _init_parser(self) -> None:
        """初始化解析器。"""
        try:
            if self.language == "python":
                import tree_sitter_python as tspython
                from tree_sitter import Language, Parser

                python_language = Language(tspython.language())
                self._parser = Parser(python_language)
            else:
                logger.warning(
                    "Language '%s' not explicitly supported, "
                    "falling back to regex-based chunking",
                    self.language,
                )
        except ImportError:
            logger.warning("tree-sitter not installed, falling back to regex-based chunking")

    def chunk(self, file_path: str, source_code: bytes | str) -> list[CodeChunk]:
        """AST 感知的代码分块。

        Args:
            file_path: 文件路径。
            source_code: 来源代码。

        Returns:
            结果列表。
        """
        if isinstance(source_code, str):
            source_code = source_code.encode("utf-8")

        if self._parser is not None:
            return self._ast_aware_chunk(file_path, source_code)
        else:
            return self._regex_fallback_chunk(file_path, source_code)

    def _ast_aware_chunk(
        self,
        file_path: str,
        source_code: bytes,
    ) -> list[CodeChunk]:
        """处理AST分块。

        Args:
            file_path: 文件路径。
            source_code: 来源代码。

        Returns:
            结果列表。
        """
        assert self._parser is not None, "AST parser not initialized"
        tree = self._parser.parse(source_code)
        root_node = tree.root_node
        chunks: list[CodeChunk] = []

        for child in root_node.children:
            if child.type == "class_definition":
                # 类整体作为一个 chunk
                class_text = source_code[child.start_byte : child.end_byte].decode()
                class_name = self._extract_class_name(child, source_code)
                chunks.append(
                    CodeChunk(
                        content=class_text,
                        metadata={
                            "file_path": file_path,
                            "type": "class",
                            "name": class_name,
                            "methods": self._extract_method_names(child, source_code),
                            "imports": self._extract_imports(root_node, source_code),
                        },
                    )
                )
                # 类的每个方法也单独作为一个 chunk
                for method in self._find_child_nodes(child, "function_definition"):
                    method_text = source_code[method.start_byte : method.end_byte].decode()
                    chunks.append(
                        CodeChunk(
                            content=method_text,
                            metadata={
                                "file_path": file_path,
                                "type": "method",
                                "class": class_name,
                                "name": self._extract_function_name(method, source_code),
                                "signature": self._extract_signature(method, source_code),
                                "imports": self._extract_imports(root_node, source_code),
                            },
                        )
                    )

            elif child.type == "function_definition":
                # 顶层函数作为一个 chunk
                func_text = source_code[child.start_byte : child.end_byte].decode()
                chunks.append(
                    CodeChunk(
                        content=func_text,
                        metadata={
                            "file_path": file_path,
                            "type": "function",
                            "name": self._extract_function_name(child, source_code),
                            "signature": self._extract_signature(child, source_code),
                            "imports": self._extract_imports(root_node, source_code),
                        },
                    )
                )

        return chunks

    def _regex_fallback_chunk(
        self,
        file_path: str,
        source_code: bytes,
    ) -> list[CodeChunk]:
        """处理正则分块。

        Args:
            file_path: 文件路径。
            source_code: 来源代码。

        Returns:
            结果列表。
        """
        import re

        text = source_code.decode("utf-8")
        chunks: list[CodeChunk] = []

        # 提取 import 语句
        imports = re.findall(
            r"^(?:import\s+\S+|from\s+\S+\s+import\s+.+)$",
            text,
            re.MULTILINE,
        )

        # 匹配类和函数定义
        pattern = r"((?:class|def)\s+\w+.*?(?=\nclass |\ndef |\Z))"
        inside_class = False
        for match in re.finditer(pattern, text, re.DOTALL):
            content = match.group(0).strip()
            chunk_type = "class" if content.startswith("class") else "function"
            name_match = re.match(r"(?:class|def)\s+(\w+)", content)
            name = name_match.group(1) if name_match else "unknown"

            # 检测 def 是否在类内（有缩进 → 方法）
            if chunk_type == "function":
                match_start = match.start()
                line_start = text.rfind("\n", 0, match_start) + 1
                leading_ws = text[line_start:match_start]
                if leading_ws and inside_class:
                    chunk_type = "method"
                else:
                    inside_class = False  # 顶层 def，不再在类内

            if chunk_type == "class":
                inside_class = True

            metadata: dict[str, Any] = {
                "file_path": file_path,
                "type": chunk_type,
                "name": name,
            }

            # 类分块：提取方法名列表
            if chunk_type == "class":
                method_names = re.findall(r"def\s+(\w+)\s*\(", content)
                metadata["methods"] = method_names

                # 为每个方法创建独立 chunk
                for method_name in method_names:
                    method_pattern = (
                        rf"(def\s+{re.escape(method_name)}\s*\(.*?"
                        r"(?=\n    def |\nclass |\ndef |\Z))"
                    )
                    method_match = re.search(method_pattern, content, re.DOTALL)
                    if method_match:
                        method_content = method_match.group(0).strip()
                        chunks.append(
                            CodeChunk(
                                content=method_content,
                                metadata={
                                    "file_path": file_path,
                                    "type": "method",
                                    "name": method_name,
                                },
                            )
                        )

            # 第一个分块附带 imports
            if not chunks and imports:
                metadata["imports"] = imports

            chunks.append(
                CodeChunk(
                    content=content,
                    metadata=metadata,
                )
            )

        # 没有 class/def 但有 import 的情况
        if not chunks and imports:
            chunks.append(
                CodeChunk(
                    content="\n".join(imports),
                    metadata={
                        "file_path": file_path,
                        "type": "imports",
                        "name": "imports",
                        "imports": imports,
                    },
                )
            )

        return chunks

    def _extract_class_name(self, node: Any, source: bytes) -> str:
        """从 AST 节点提取类名。

        Args:
            node: 待处理节点。
            source: 调用或事件来源。

        Returns:
            字符串结果。
        """
        for child in node.children:
            if child.type == "identifier":
                return source[child.start_byte : child.end_byte].decode()
        return "unknown"

    def _extract_function_name(self, node: Any, source: bytes) -> str:
        """从 AST 节点提取函数名。

        Args:
            node: 待处理节点。
            source: 调用或事件来源。

        Returns:
            字符串结果。
        """
        for child in node.children:
            if child.type == "identifier":
                return source[child.start_byte : child.end_byte].decode()
        return "unknown"

    def _extract_method_names(self, class_node: Any, source: bytes) -> list[str]:
        """从类节点提取所有方法名。

        Args:
            class_node: 类。
            source: 调用或事件来源。

        Returns:
            结果列表。
        """
        methods: list[str] = []
        for child in self._find_child_nodes(class_node, "function_definition"):
            methods.append(self._extract_function_name(child, source))
        return methods

    def _extract_signature(self, node: Any, source: bytes) -> str:
        """从 AST 节点提取函数签名。

        Args:
            node: 待处理节点。
            source: 调用或事件来源。

        Returns:
            字符串结果。
        """
        for child in node.children:
            if child.type == "parameters":
                return source[node.start_byte : child.end_byte].decode()
        return ""

    def _extract_imports(self, root_node: Any, source: bytes) -> list[str]:
        """提取导入。

        Args:
            root_node: 根。
            source: 调用或事件来源。

        Returns:
            结果列表。
        """
        imports: list[str] = []
        for child in root_node.children:
            if child.type in ("import_statement", "import_from_statement"):
                imports.append(source[child.start_byte : child.end_byte].decode())
        return imports

    def _find_child_nodes(self, node: Any, node_type: str) -> list[Any]:
        """递归查找指定类型的子节点。

        Args:
            node: 待处理节点。
            node_type: 节点类型。

        Returns:
            结果列表。
        """
        result: list[Any] = []
        for child in node.children:
            if child.type == node_type:
                result.append(child)
            result.extend(self._find_child_nodes(child, node_type))
        return result
