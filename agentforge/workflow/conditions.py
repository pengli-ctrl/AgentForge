"""条件表达式解析器 — 解析工作流 YAML 中的条件路由表达式。

解析形如以下的条件表达式：
    "result.severity == 'critical'"
    "result.pass_rate < 0.8"
    "result.has_vulnerabilities"
    "default"

支持的操作符：
- == : 等于
- != : 不等于
- >  : 大于
- <  : 小于
- >= : 大于等于
- <= : 小于等于
- in : 包含在列表中

支持的数据类型：
- 字符串（单引号或双引号）
- 数字（整数和浮点数）
- 布尔值（true/false）
- None/null

设计原则：
- 安全性：不使用 eval()，通过正则解析 + 受限求值
- 可扩展：支持自定义操作符和函数
- 可调试：解析错误时提供清晰的错误信息
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class ConditionParser:
    """条件表达式解析器 — 解析和求值工作流路由条件。

    将条件字符串解析为 AST，然后对 Agent 输出结果求值。
    不使用 eval()，通过正则解析确保安全性。

    Example:
        >>> parser = ConditionParser()
        >>> parser.evaluate("result.severity == 'critical'",
        ...                 {"result": {"severity": "critical"}})
        True
        >>> parser.evaluate("result.pass_rate < 0.8",
        ...                 {"result": {"pass_rate": 0.6}})
        True
    """

    # 操作符正则（按优先级排列，先匹配长操作符）
    _OPERATOR_PATTERN = re.compile(r"(==|!=|>=|<=|>|<|\bin\b)")

    # 支持的操作符到 Python 比较函数的映射
    _OPERATORS: dict[str, Any] = {
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        ">": lambda a, b: a > b,
        "<": lambda a, b: a < b,
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
        "in": lambda a, b: a in b,
    }

    def evaluate(self, condition: str, context: dict[str, Any]) -> bool:
        """解析并求值条件表达式。

        Args:
            condition: 条件字符串（如 "result.severity == 'critical'"）。
            context: 求值上下文（Agent 输出结果）。

        Returns:
            条件是否满足。

        Raises:
            ValueError: 条件表达式格式错误时抛出。
        """
        condition = condition.strip()

        # "default" 是特殊条件，始终返回 True
        if condition == "default":
            return True

        # 简单布尔检查：只有路径没有操作符
        if not self._OPERATOR_PATTERN.search(condition):
            value = self._resolve_path(condition, context)
            return bool(value)

        # 解析操作符
        match = self._OPERATOR_PATTERN.search(condition)
        if not match:
            raise ValueError(f"Invalid condition: {condition}")

        operator = match.group(1)
        left_part = condition[: match.start()].strip()
        right_part = condition[match.end() :].strip()

        left_value = self._resolve_path(left_part, context)
        right_value = self._parse_literal(right_part, context)

        op_func = self._OPERATORS.get(operator)
        if op_func is None:
            raise ValueError(f"Unsupported operator: {operator}")

        try:
            result = op_func(left_value, right_value)
            logger.debug(
                "Condition evaluated (condition=%s, left=%s, right=%s, result=%s)",
                condition,
                left_value,
                right_value,
                result,
            )
            return result
        except TypeError as e:
            logger.warning(
                "Condition evaluation failed (condition=%s, error=%s)",
                condition,
                e,
            )
            return False

    def _resolve_path(self, path: str, context: dict[str, Any]) -> Any:
        """解析点分隔的属性路径。

        如 "result.severity" 从 context 中解析为 context["result"]["severity"]。

        Args:
            path: 点分隔的属性路径。
            context: 求值上下文。

        Returns:
            解析出的值，路径不存在则返回 None。
        """
        parts = path.split(".")
        current: Any = context

        for part in parts:
            part = part.strip()
            if isinstance(current, dict):
                current = current.get(part)
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None

            if current is None:
                return None

        return current

    def _parse_literal(self, literal: str, context: dict[str, Any]) -> Any:
        """解析字面量值。

        支持的类型：
        - 字符串（单引号或双引号包裹）
        - 数字（整数和浮点数）
        - 布尔值（true/false）
        - None/null
        - 属性路径（如 result.severity）

        Args:
            literal: 字面量字符串。
            context: 求值上下文。

        Returns:
            解析出的值。
        """
        literal = literal.strip()

        # 字符串字面量
        if (literal.startswith("'") and literal.endswith("'")) or (
            literal.startswith('"') and literal.endswith('"')
        ):
            return literal[1:-1]

        # 布尔值
        if literal.lower() == "true":
            return True
        if literal.lower() == "false":
            return False

        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        if literal.lower() in ("none", "null"):
            return None

        # 数字
        try:
            if "." in literal:
                return float(literal)
            return int(literal)
        except ValueError:
            pass

        # 属性路径
        return self._resolve_path(literal, context)
