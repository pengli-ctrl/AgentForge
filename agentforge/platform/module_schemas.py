"""模块结构模块。"""

from __future__ import annotations

import re

_MODULE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
MODULE_SCHEMAS: dict[str, str] = {
    "support": "module_support",
    "expense": "module_expense",
}


def module_schema_name(module_name: str) -> str:
    """处理模块结构名称。

    Args:
        module_name: 模块名称。

    Returns:
        字符串结果。

    Raises:
        ValueError: 输入值或业务状态不合法时抛出。
    """
    if not _MODULE_NAME.fullmatch(module_name):
        raise ValueError("invalid module name")
    try:
        return MODULE_SCHEMAS[module_name]
    except KeyError as exc:
        raise ValueError(f"module schema is not configured: {module_name}") from exc
