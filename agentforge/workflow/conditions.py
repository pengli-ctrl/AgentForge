"""条件模块。"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class ConditionParser:
    """条件表达式解析器 — 解析和求值工作流路由条件。

    Attributes:
        _OPERATORS: 字段值。
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
            condition: 输入参数。
            context: 执行上下文。

        Returns:
            操作是否成功。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
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

        Args:
            path: 文件或资源路径。
            context: 执行上下文。

        Returns:
            处理结果对象。
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

        Args:
            literal: 输入参数。
            context: 执行上下文。

        Returns:
            处理结果对象。
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
