"""平台模块依赖边界测试。"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PLATFORM_ROOT = REPO_ROOT / "agentforge" / "platform"


def _python_files(root: Path) -> Iterator[Path]:
    """处理文件。

    Args:
        root: 根。

    Yields:
        逐次生成的结果。
    """
    for path in root.rglob("*.py"):
        if "__pycache__" not in path.parts:
            yield path


def _imports(path: Path) -> set[str]:
    """处理导入。

    Args:
        path: 文件或资源路径。

    Returns:
        设置结果。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _assert_no_import(root: Path, forbidden_prefixes: tuple[str, ...]) -> None:
    """处理无导入。

    Args:
        root: 根。
        forbidden_prefixes: 输入参数。
    """
    violations: list[str] = []
    for path in _python_files(root):
        for imported in _imports(path):
            if any(
                imported == prefix or imported.startswith(f"{prefix}.")
                for prefix in forbidden_prefixes
            ):
                violations.append(f"{path.relative_to(REPO_ROOT)} -> {imported}")
    assert not violations, "\n".join(violations)


def test_core_does_not_import_business_modules() -> None:
    """验证核心会不导入模块对应的测试场景。"""
    _assert_no_import(PLATFORM_ROOT / "core", ("agentforge.platform.modules",))


def test_sdk_does_not_import_core_or_business_modules() -> None:
    """验证SDK会不导入核心或模块对应的测试场景。"""
    _assert_no_import(
        PLATFORM_ROOT / "sdk",
        ("agentforge.platform.core", "agentforge.platform.modules"),
    )


def test_modules_do_not_import_core_or_other_modules() -> None:
    """验证模块执行不导入核心或模块对应的测试场景。"""
    modules_root = PLATFORM_ROOT / "modules"
    module_dirs = [path for path in modules_root.iterdir() if path.is_dir()]
    for module_dir in module_dirs:
        own_prefix = f"agentforge.platform.modules.{module_dir.name}"
        allowed = (own_prefix,)
        violations: list[str] = []
        for path in _python_files(module_dir):
            for imported in _imports(path):
                if imported.startswith("agentforge.platform.core"):
                    violations.append(f"{path.relative_to(REPO_ROOT)} -> {imported}")
                if imported.startswith("agentforge.platform.modules.") and not any(
                    imported == prefix or imported.startswith(f"{prefix}.") for prefix in allowed
                ):
                    violations.append(f"{path.relative_to(REPO_ROOT)} -> {imported}")
        assert not violations, "\n".join(violations)


def test_runtime_does_not_import_business_modules() -> None:
    """验证运行时会不导入模块对应的测试场景。"""
    runtime_path = PLATFORM_ROOT / "runtime.py"
    violations = [
        imported
        for imported in _imports(runtime_path)
        if imported == "agentforge.platform.modules"
        or imported.startswith("agentforge.platform.modules.")
    ]
    assert not violations, "\n".join(violations)


def test_sdk_does_not_import_platform_implementations() -> None:
    """验证SDK会不导入平台对应的测试场景。"""
    _assert_no_import(
        PLATFORM_ROOT / "sdk",
        (
            "agentforge.platform.api",
            "agentforge.platform.application",
            "agentforge.platform.core",
            "agentforge.platform.infrastructure",
            "agentforge.platform.modules",
            "agentforge.platform.runtime",
        ),
    )


def test_modules_do_not_import_platform_runtime_application_api_or_core() -> None:
    """验证模块执行不导入平台运行时应用API或核心对应的测试场景。"""
    _assert_no_import(
        PLATFORM_ROOT / "modules",
        (
            "agentforge.platform.api",
            "agentforge.platform.application",
            "agentforge.platform.core",
            "agentforge.platform.runtime",
        ),
    )


def test_module_domain_application_and_api_do_not_import_platform_infrastructure() -> None:
    """验证模块领域应用及API执行不导入平台基础设施对应的测试场景。"""
    modules_root = PLATFORM_ROOT / "modules"
    for module_dir in (path for path in modules_root.iterdir() if path.is_dir()):
        for layer in ("domain", "application", "api"):
            layer_root = module_dir / layer
            if layer_root.exists():
                _assert_no_import(layer_root, ("agentforge.platform.infrastructure",))
