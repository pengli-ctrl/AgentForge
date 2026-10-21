"""验证项目代码的 Google 风格文档字符串质量。"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CODE_GROUPS = ("agentforge", "scripts", "bench", "examples", "templates", "tests", "alembic")
GENERIC_RE = re.compile(
    r"(执行 .* 对应的逻辑|执行 .* 对应的操作|"
    r"业务项类型|相关逻辑|创建新的业务对象|"
    r"读取并返回指定数据|返回调用方需要的结果|"
    r"调用方传入的|函数执行后的结果|说明：该步骤|保持职责单一并降低调用方复杂度|"
    r"封装相关领域行为|设计约束：|主要成员：|^Compute and return the .* result|"
    r"^Execute .* operation|^Encapsulates .* behavior|^Domain component representing |\?{3,}|�)",
    re.IGNORECASE,
)
SECTION_RE = re.compile(r"^\s*(Args|Returns|Raises|Yields|Attributes):\s*$", re.MULTILINE)


def _python_files(group: str) -> list[Path]:
    """返回指定代码分组下的 Python 文件，并排除字节码缓存。

    Args:
        group: 输入参数。

    Returns:
        结果列表。
    """
    base = ROOT / group
    if not base.exists():
        return []
    return [path for path in base.rglob("*.py") if "__pycache__" not in path.parts]


def _has_direct_raise(node: ast.AST) -> bool:
    """判断函数体内是否直接抛出异常，忽略嵌套函数和类。

    Args:
        node: 待处理节点。

    Returns:
        操作是否成功。
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(child, ast.Raise):
            return True
        if _has_direct_raise(child):
            return True
    return False


def _has_chinese(text: str) -> bool:
    """判断文本是否包含中文字符。

    Args:
        text: 待处理文本。

    Returns:
        操作是否成功。
    """
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _has_untranslated_latin(text: str) -> bool:
    """判断摘要中是否仍有未翻译的小写英文单词。

    Args:
        text: 待检查的摘要文本。

    Returns:
        存在未翻译英文单词时返回 True。
    """
    masked = re.sub(r"/[^\s，。]+", "", text)
    masked = re.sub(r"__[A-Za-z_]+__", "", masked)
    masked = re.sub(r"`[^`]+`", "", masked)
    allowed = {"pytest", "httpx", "v1"}
    return any(
        word not in allowed
        for word in re.findall(r"(?<![A-Za-z0-9_])[a-z][a-z0-9_-]*(?![A-Za-z0-9_])", masked)
    )


def _doc_issues(path: Path, node: ast.AST, doc: str | None, kind: str) -> list[str]:
    """检查单个模块、类或函数是否符合 Google 风格要求。

    Args:
        path: 文件或资源路径。
        node: 待处理节点。
        doc: 输入参数。
        kind: 输入参数。

    Returns:
        结果列表。
    """
    issues: list[str] = []
    location = f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 1)}"
    name = getattr(node, "name", "<module>")
    if not doc or not doc.strip() or GENERIC_RE.search(doc):
        return [f"{location}:{name}: 缺少有效 docstring"]
    summary = doc.strip().splitlines()[0].strip()
    if not _has_chinese(summary):
        issues.append(f"{location}:{name}: 摘要必须使用中文")
    elif _has_untranslated_latin(summary):
        issues.append(f"{location}:{name}: 摘要仍包含未翻译英文")
    elif re.search(r"(.{2,6})\1", summary):
        issues.append(f"{location}:{name}: 摘要存在重复片段")
    sections = set(SECTION_RE.findall(doc))
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = [
            arg
            for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            if arg.arg not in {"self", "cls"}
        ]
        if node.args.vararg is not None:
            args.append(node.args.vararg)
        if node.args.kwarg is not None:
            args.append(node.args.kwarg)
        if args and "Args" not in sections:
            issues.append(f"{location}:{name}: 有参数但缺少 Args:")
        if args and "Args" in sections:
            for arg in args:
                if f"{arg.arg}:" not in doc:
                    issues.append(f"{location}:{name}: Args 缺少参数 {arg.arg}")
        has_yield = any(isinstance(child, ast.Yield) for child in ast.walk(node))
        if has_yield and "Yields" not in sections:
            issues.append(f"{location}:{name}: 生成器缺少 Yields:")
        if not has_yield and node.returns is not None:
            return_text = ast.unparse(node.returns)
            if return_text not in {"None", "NoneType"} and "Returns" not in sections:
                issues.append(f"{location}:{name}: 有返回值但缺少 Returns:")
        if _has_direct_raise(node) and "Raises" not in sections:
            issues.append(f"{location}:{name}: 有异常但缺少 Raises:")
    if isinstance(node, ast.ClassDef):
        fields = [
            child
            for child in node.body
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name)
        ]
        if fields and "Attributes" not in sections:
            issues.append(f"{location}:{name}: 有字段但缺少 Attributes:")
        if fields and "Attributes" in sections:
            for field in fields:
                if f"{field.target.id}:" not in doc:
                    issues.append(f"{location}:{name}: Attributes 缺少字段 {field.target.id}")
    return issues


def _collect_issues(path: Path) -> list[str]:
    """收集一个 Python 文件中的文档字符串问题。

    Args:
        path: 文件或资源路径。

    Returns:
        结果列表。
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    issues = _doc_issues(path, tree, ast.get_docstring(tree, clean=False), "module")

    def walk(nodes: list[ast.stmt]) -> None:
        """递归检查嵌套类、方法和函数。

        Args:
            nodes: 输入参数。
        """
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                issues.extend(
                    _doc_issues(path, node, ast.get_docstring(node, clean=False), "class")
                )
                walk(node.body)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                issues.extend(
                    _doc_issues(path, node, ast.get_docstring(node, clean=False), "function")
                )
                walk(node.body)

    walk(tree.body)
    return issues


def test_code_uses_chinese_google_docstrings() -> None:
    """验证代码使用对应的测试场景。"""
    issues: list[str] = []
    for group in CODE_GROUPS:
        for path in _python_files(group):
            issues.extend(_collect_issues(path))
    assert not issues, "Google 风格文档字符串问题：\n" + "\n".join(issues)


def test_no_template_comments_remain() -> None:
    """拒绝不解释行为且由模板批量生成的注释。"""
    issues: list[str] = []
    for group in (*CODE_GROUPS, "tests"):
        for path in _python_files(group):
            if path.name == "test_docstrings.py":
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if GENERIC_RE.search(line):
                    issues.append(f"{path.relative_to(ROOT)}:{lineno}:{line.strip()}")
    assert not issues, "仍存在模板化注释：\n" + "\n".join(issues)


def test_comments_use_chinese_or_code_directives() -> None:
    """要求普通行注释使用中文，并允许标准工具指令保持原文。"""
    issues: list[str] = []
    allowed_prefixes = (
        "noqa",
        "type:",
        "pragma",
        "fmt:",
        "isort:",
        "mypy:",
        "pyright:",
        "nosec",
        "-*-",
    )
    for group in CODE_GROUPS:
        for path in _python_files(group):
            source = path.read_text(encoding="utf-8")
            for token in tokenize.generate_tokens(io.StringIO(source).readline):
                if token.type != tokenize.COMMENT:
                    continue
                value = token.string.lstrip("#").strip()
                if not value or value.startswith(allowed_prefixes):
                    continue
                if not _has_chinese(value):
                    issues.append(f"{path.relative_to(ROOT)}:{token.start[0]}: {value}")
    assert not issues, "?????????????\n" + "\n".join(issues)
