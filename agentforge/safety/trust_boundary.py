"""信任边界模块。"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """校验结果相关组件。

    Attributes:
        passed: 通过。
        errors: 字段值。
    """

    passed: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class FieldRef:
    """字段引用相关组件。

    Attributes:
        api_name: API名称。
        field: 字段。
    """

    api_name: str = ""
    field: str = ""


class TrustBoundary:
    """跨来源事实的可信边界校验器。

    Attributes:
        DETERMINISTIC_RULES: 规则。
    """

    # 确定性规则：不依赖 LLM 判断，直接查表 / 查 Schema
    DETERMINISTIC_RULES: dict[str, Any] = {
        # 操作类型白名单：某些业务操作禁止特定实现方式
        "forbidden_operations": {
            "user_deactivation": ["DELETE", "TRUNCATE"],  # 只允许 UPDATE status
            "order_cancellation": ["DELETE"],  # 订单禁止物理删除
            "log_entry": ["DELETE", "UPDATE"],  # 日志禁止修改和删除
        },
        # API 字段名必须在 API Schema 中
        "api_field_names": True,
        # 函数名必须在已知接口注册表中
        "function_names": True,
        # 数值型字段必须在合理范围内
        "value_ranges": True,
    }

    # 匹配 api_name.field_name 模式的正则（排除常见非 API 引用）
    _DOT_PATTERN = re.compile(r"\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b", re.IGNORECASE)

    # 匹配 api_name["field_name"] 或 api_name['field_name'] 模式
    _BRACKET_DQ_PATTERN = re.compile(r'\b([a-z_][a-z0-9_]*)\["([a-z_][a-z0-9_]*)"\]', re.IGNORECASE)
    _BRACKET_SQ_PATTERN = re.compile(r"\b([a-z_][a-z0-9_]*)\['([a-z_][a-z0-9_]*)'\]", re.IGNORECASE)

    # 需要排除的常见非 API 引用（避免误报）
    _EXCLUDE_PREFIXES = {
        "http",
        "https",
        "ftp",
        "file",
        "www",
        "com",
        "org",
        "self",
        "cls",
        "type",
        "dict",
        "list",
        "str",
        "int",
        "float",
        "bool",
        "true",
        "false",
        "none",
        "null",
    }

    def __init__(self, api_schema: dict[str, list[str]] | None = None) -> None:
        """初始化 TrustBoundary。

        Args:
            api_schema: API结构。
        """
        self.api_schema = api_schema or {}

    def validate(
        self,
        agent_output: dict[str, Any],
        context: dict[str, Any],
    ) -> ValidationResult:
        """校验信任边界。

        Args:
            agent_output: 智能体输出。
            context: 执行上下文。

        Returns:
            校验结果结果。
        """
        errors: list[str] = []

        # 第一层：确定性规则校验
        operation = self._extract_operation(agent_output)
        business_action = context.get("business_action")

        if business_action in self.DETERMINISTIC_RULES["forbidden_operations"]:
            forbidden = self.DETERMINISTIC_RULES["forbidden_operations"][business_action]
            if operation and operation.type in forbidden:
                errors.append(
                    f"Operation '{operation.type}' is forbidden for "
                    f"'{business_action}'. "
                    f"Expected: UPDATE with status field."
                )

        # 校验 API 字段名
        if self.DETERMINISTIC_RULES["api_field_names"]:
            for field_ref in self._extract_field_references(agent_output):
                if field_ref.api_name and field_ref.field not in self.api_schema.get(
                    field_ref.api_name, []
                ):
                    errors.append(f"Unknown field '{field_ref.field}' for API {field_ref.api_name}")

        logger.info(
            "TrustBoundary validation (passed=%s, errors=%d)",
            len(errors) == 0,
            len(errors),
        )

        return ValidationResult(passed=len(errors) == 0, errors=errors)

    def _extract_operation(self, output: dict[str, Any]) -> Any:
        """提取操作。

        Args:
            output: 输出。

        Returns:
            处理结果对象。
        """

        class _Operation:
            """操作相关组件。"""

            def __init__(self, op_type: str = "") -> None:
                """初始化 _Operation。

                Args:
                    op_type: 操作类型。
                """
                self.type = op_type

        # 从 SQL 语句中提取操作类型
        sql = output.get("sql", "")
        if sql:
            sql_upper = sql.strip().upper()
            for op in ("DELETE", "TRUNCATE", "UPDATE", "INSERT", "SELECT"):
                if sql_upper.startswith(op):
                    return _Operation(op)

        return _Operation()

    def _extract_field_references(self, output: dict[str, Any]) -> list[FieldRef]:
        """提取字段。

        Args:
            output: 输出。

        Returns:
            结果列表。
        """
        # 将输出转为可搜索的文本
        text = self._output_to_text(output)

        refs: list[FieldRef] = []
        seen: set[tuple[str, str]] = set()

        # 匹配 api_name["field_name"] 和 api_name['field_name']
        for pattern in (self._BRACKET_DQ_PATTERN, self._BRACKET_SQ_PATTERN):
            for match in pattern.finditer(text):
                api_name = match.group(1).lower()
                field_name = match.group(2).lower()
                if api_name not in self._EXCLUDE_PREFIXES:
                    key = (api_name, field_name)
                    if key not in seen:
                        seen.add(key)
                        refs.append(FieldRef(api_name=api_name, field=field_name))

        # 匹配 api_name.field_name
        for match in self._DOT_PATTERN.finditer(text):
            api_name = match.group(1).lower()
            field_name = match.group(2).lower()
            if api_name not in self._EXCLUDE_PREFIXES:
                key = (api_name, field_name)
                if key not in seen:
                    seen.add(key)
                    refs.append(FieldRef(api_name=api_name, field=field_name))

        return refs

    def _output_to_text(self, output: Any) -> str:
        """处理输出到文本。

        Args:
            output: 输出。

        Returns:
            字符串结果。
        """
        parts: list[str] = []

        def _extract(obj: Any) -> None:
            """提取信任边界。

            Args:
                obj: 输入参数。
            """
            if isinstance(obj, str):
                parts.append(obj)
            elif isinstance(obj, dict):
                for value in obj.values():
                    _extract(value)
            elif isinstance(obj, (list, tuple)):
                for item in obj:
                    _extract(item)

        _extract(output)

        # 也包含 JSON 序列化的完整输出（捕获更复杂的嵌套引用）
        try:
            parts.append(json.dumps(output, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            pass

        return " ".join(parts)


class CrossSourceVerifier:
    """异源验证器 — 关键业务决策必须由不同知识源交叉验证。"""

    def __init__(
        self,
        rule_engine: Any = None,
        schema_dict: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """初始化异源验证器。

        Args:
            rule_engine: 规则引擎。
            schema_dict: 结构字典。
        """
        self.rule_engine = rule_engine
        self.schema_dict = schema_dict or {}

    async def verify(
        self,
        primary_output: dict[str, Any],
        business_context: Any,
    ) -> Any:
        """对关键业务操作进行异源交叉验证。

        Args:
            primary_output: 输出。
            business_context: 上下文。

        Returns:
            处理结果对象。
        """

        class _VerificationResult:
            """核验结果领域组件。"""

            def __init__(self) -> None:
                """初始化 _VerificationResult。"""
                self.passed = True
                self.violations: list[str] = []

        result = _VerificationResult()

        # 从数据库 Schema 提取约束（确定性知识源，非 LLM）
        schema_constraints = await self._load_schema_constraints(
            getattr(business_context, "target_tables", [])
        )

        # 从业务规则引擎提取规则（人工维护的确定性规则）
        business_rules: list[Any] = []
        if self.rule_engine:
            business_rules = self.rule_engine.get_rules(getattr(business_context, "action", ""))

        # 用确定性代码验证 LLM 生成的代码是否符合这些约束
        for rule in business_rules:
            if not rule.check(primary_output, schema_constraints):
                result.passed = False
                result.violations.append(f"Business rule violated: {rule.description}")

        return result

    async def _load_schema_constraints(self, target_tables: list[str]) -> dict[str, Any]:
        """加载结构约束。

        Args:
            target_tables: 目标。

        Returns:
            结构化结果字典。
        """
        if not self.schema_dict:
            return {}

        constraints: dict[str, Any] = {}
        for table in target_tables:
            if table in self.schema_dict:
                constraints[table] = self.schema_dict[table]
            else:
                # 表名大小写不敏感查找
                for key, value in self.schema_dict.items():
                    if key.lower() == table.lower():
                        constraints[table] = value
                        break

        return constraints
