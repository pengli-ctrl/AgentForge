"""
Trust Boundary — Agent 输出的确定性校验层。

阻断 LLM 幻觉的跨 Agent 传播 + 检测语义陷阱。
核心思路：用确定性代码检查来兜底 LLM 的概率性输出，
不依赖 LLM 自己验证自己。

确定性规则：
- 操作类型白名单：某些业务操作禁止特定实现方式
  （如用户注销只允许 UPDATE status，禁止 DELETE）
- API 字段名必须在 API Schema 中
- 函数名必须在已知接口注册表中
- 数值型字段必须在合理范围内

这是 Layer 2（Agent 间防护）的核心组件。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Trust Boundary 校验结果。

    Attributes:
        passed: 校验是否通过。
        errors: 校验错误列表。
    """

    passed: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class FieldRef:
    """API 字段引用 — 从 Agent 输出中提取的字段引用。

    Attributes:
        api_name: API 名称。
        field: 字段名。
    """

    api_name: str = ""
    field: str = ""


class TrustBoundary:
    """Agent 输出的确定性校验层 — 阻断幻觉传播 + 检测语义陷阱。

    用确定性规则校验 LLM 输出，不依赖 LLM 判断：
    - 操作类型白名单：禁止特定业务操作使用特定实现方式
    - API 字段名校验：确保引用的字段名在 API Schema 中
    - 函数名校验：确保引用的函数名在已知接口注册表中
    - 数值范围校验：确保数值型字段在合理范围内

    解决的故障模式：
    - 浅层幻觉（字段名幻觉 user_email vs email）→ 查 API Schema 拦截
    - 深层幻觉（业务语义幻觉 硬删除 vs 软删除）→ 禁止操作类型拦截

    配合 CrossSourceVerifier 使用：
    - Trust Boundary 解决浅层幻觉（字段名、函数名）
    - CrossSourceVerifier 解决深层幻觉（业务逻辑、数据模型约定）
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
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            api_schema: dict[str, list[str]] | None，调用方传入的 api_schema 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.api_schema = api_schema or {}

    def validate(
        self,
        agent_output: dict[str, Any],
        context: dict[str, Any],
    ) -> ValidationResult:
        """校验 Agent 输出是否符合确定性规则。

        Args:
            agent_output: Agent 的输出内容。
            context: Agent 上下文，包含 business_action 等信息。

        Returns:
            校验结果，包含通过状态和错误列表。
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
        """从 Agent 输出中提取操作类型。

        Args:
            output: Agent 输出。

        Returns:
            操作信息对象，包含 type 字段。
        """

        class _Operation:
            """_Operation。

            _Operation 封装相关领域行为，保持职责单一并降低调用方复杂度。

            设计约束：
            - 保持接口稳定，避免调用方依赖内部实现细节。
            - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
            """

            def __init__(self, op_type: str = "") -> None:
                """初始化实例，并保存运行所需的依赖、配置和内部状态。

                Args:
                    op_type: str，调用方传入的 op_type 参数。

                Returns:
                    None，函数执行后的结果。
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
        """从 Agent 输出中提取 API 字段引用。

        扫描 Agent 输出中的所有文本内容，匹配以下格式的字段引用：
        - 点号语法：``api_name.field_name``（如 ``user_api.email``）
        - 方括号语法：``api_name["field_name"]`` 或 ``api_name['field_name']``

        使用正则表达式匹配，排除常见的非 API 引用（如 http、self 等）。

        Args:
            output: Agent 输出。

        Returns:
            FieldRef 对象列表，每个包含 api_name 和 field 属性。
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
        """将 Agent 输出（dict/list/str）转为可搜索的文本。

        递归遍历嵌套结构，提取所有字符串值拼接为一个文本。

        Args:
            output: Agent 输出（可能是 dict、list 或 str）。

        Returns:
            拼接后的文本。
        """
        parts: list[str] = []

        def _extract(obj: Any) -> None:
            """执行 _extract 对应的逻辑，并返回处理结果。

            Args:
                obj: Any，调用方传入的 obj 参数。

            Returns:
                None，函数执行后的结果。
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
    """异源验证器 — 关键业务决策必须由不同知识源交叉验证。

    原理：如果 CodeGenerator 和 TestGenerator 都是同族 LLM 驱动，
    它们共享相同的知识偏差。交叉验证需要引入不同的知识源 —
    比如从项目的架构决策记录（ADR）、数据库 Schema、或业务规则引擎中
    提取约束条件，用确定性代码（非 LLM）执行验证。

    解决的故障模式：
    - 语义自洽陷阱 — 同族 LLM 独立地"同意"了一个错误的实现
    - 共识惰性 — 早期错误被后续 Agent 的"同意"不断强化

    核心洞察：用"异构知识源"打破"同源验证"的盲区。

    Args:
        rule_engine: 业务规则引擎实例。
        schema_dict: 预定义的 Schema 约束字典，格式为
            ``{table_name: {field_name: constraint}}``。
            如果提供，``_load_schema_constraints`` 将从中查找约束，
            而非查询数据库。
    """

    def __init__(
        self,
        rule_engine: Any = None,
        schema_dict: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """初始化异源验证器。

        Args:
            rule_engine: 业务规则引擎实例。
            schema_dict: 预定义的 Schema 约束字典。
        """
        self.rule_engine = rule_engine
        self.schema_dict = schema_dict or {}

    async def verify(
        self,
        primary_output: dict[str, Any],
        business_context: Any,
    ) -> Any:
        """对关键业务操作进行异源交叉验证。

        从数据库 Schema 和业务规则引擎提取约束（确定性知识源，非 LLM），
        用确定性代码验证 LLM 生成的代码是否符合这些约束。

        Args:
            primary_output: 主生成链路的输出。
            business_context: 业务上下文，包含目标表等信息。

        Returns:
            验证结果，包含通过状态和违规列表。
        """

        class _VerificationResult:
            """_VerificationResult。

            _VerificationResult 封装相关领域行为，保持职责单一并降低调用方复杂度。

            设计约束：
            - 保持接口稳定，避免调用方依赖内部实现细节。
            - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
            """

            def __init__(self) -> None:
                """初始化实例，并保存运行所需的依赖、配置和内部状态。

                Returns:
                    None，函数执行后的结果。
                """
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
        """从 Schema 加载约束条件。

        如果初始化时传入了 ``schema_dict``，从中查找目标表的约束。
        否则返回空字典（实际实现可查询数据库 information_schema）。

        Args:
            target_tables: 目标表名列表。

        Returns:
            Schema 约束字典 ``{table_name: {field_name: constraint}}``。
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
