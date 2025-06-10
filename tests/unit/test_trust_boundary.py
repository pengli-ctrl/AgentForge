"""Trust Boundary 单元测试 — Agent 输出的确定性校验层。

测试要点：权限校验、边界隔离、非法访问拒绝、白名单/黑名单逻辑。
"""

from __future__ import annotations

import pytest

from agentforge.safety.trust_boundary import (
    CrossSourceVerifier,
    TrustBoundary,
    ValidationResult,
)


class TestValidationResult:
    """ValidationResult 数据类测试。"""

    def test_default_passed_result(self) -> None:
        result = ValidationResult(passed=True)
        assert result.passed is True
        assert result.errors == []

    def test_failed_result_with_errors(self) -> None:
        result = ValidationResult(
            passed=False,
            errors=["field A invalid", "operation forbidden"],
        )
        assert result.passed is False
        assert len(result.errors) == 2


class TestTrustBoundaryInit:
    """TrustBoundary 初始化测试。"""

    def test_default_init_empty_schema(self) -> None:
        tb = TrustBoundary()
        assert tb.api_schema == {}

    def test_init_with_api_schema(self) -> None:
        schema = {"user_api": ["id", "name", "email"]}
        tb = TrustBoundary(api_schema=schema)
        assert tb.api_schema == schema

    def test_deterministic_rules_exist(self) -> None:
        tb = TrustBoundary()
        assert "forbidden_operations" in tb.DETERMINISTIC_RULES
        assert "api_field_names" in tb.DETERMINISTIC_RULES
        assert "function_names" in tb.DETERMINISTIC_RULES
        assert "value_ranges" in tb.DETERMINISTIC_RULES


class TestTrustBoundaryForbiddenOperations:
    """操作类型白名单 / 黑名单测试。"""

    def test_delete_blocked_for_user_deactivation(self) -> None:
        """user_deactivation 禁止 DELETE 操作。"""
        tb = TrustBoundary()
        output = {"sql": "DELETE FROM users WHERE id = 1"}
        context = {"business_action": "user_deactivation"}
        result = tb.validate(output, context)
        assert result.passed is False
        assert any("forbidden" in err.lower() for err in result.errors)

    def test_truncate_blocked_for_user_deactivation(self) -> None:
        """user_deactivation 禁止 TRUNCATE 操作。"""
        tb = TrustBoundary()
        output = {"sql": "TRUNCATE TABLE users"}
        context = {"business_action": "user_deactivation"}
        result = tb.validate(output, context)
        assert result.passed is False

    def test_update_allowed_for_user_deactivation(self) -> None:
        """user_deactivation 允许 UPDATE 操作。"""
        tb = TrustBoundary()
        output = {"sql": "UPDATE users SET status = 'inactive' WHERE id = 1"}
        context = {"business_action": "user_deactivation"}
        result = tb.validate(output, context)
        assert result.passed is True

    def test_delete_blocked_for_order_cancellation(self) -> None:
        """order_cancellation 禁止 DELETE 操作。"""
        tb = TrustBoundary()
        output = {"sql": "DELETE FROM orders WHERE id = 1"}
        context = {"business_action": "order_cancellation"}
        result = tb.validate(output, context)
        assert result.passed is False

    def test_delete_and_update_blocked_for_log_entry(self) -> None:
        """log_entry 同时禁止 DELETE 和 UPDATE。"""
        tb = TrustBoundary()

        output_del = {"sql": "DELETE FROM logs WHERE id = 1"}
        context = {"business_action": "log_entry"}
        assert tb.validate(output_del, context).passed is False

        output_upd = {"sql": "UPDATE logs SET msg = 'x' WHERE id = 1"}
        assert tb.validate(output_upd, context).passed is False

    def test_no_business_action_passes(self) -> None:
        """没有 business_action 时不应触发禁止操作规则。"""
        tb = TrustBoundary()
        output = {"sql": "DELETE FROM users WHERE id = 1"}
        context = {}
        result = tb.validate(output, context)
        assert result.passed is True


class TestTrustBoundaryExtractOperation:
    """操作类型提取测试。"""

    def test_extract_delete_operation(self) -> None:
        tb = TrustBoundary()
        op = tb._extract_operation({"sql": "DELETE FROM t"})
        assert op.type == "DELETE"

    def test_extract_truncate_operation(self) -> None:
        tb = TrustBoundary()
        op = tb._extract_operation({"sql": "truncate table t"})
        assert op.type == "TRUNCATE"

    def test_extract_update_operation(self) -> None:
        tb = TrustBoundary()
        op = tb._extract_operation({"sql": "UPDATE t SET x=1"})
        assert op.type == "UPDATE"

    def test_extract_no_sql(self) -> None:
        tb = TrustBoundary()
        op = tb._extract_operation({})
        assert op.type == ""


class TestCrossSourceVerifier:
    """CrossSourceVerifier 测试。"""

    @pytest.mark.asyncio
    async def test_verify_no_rule_engine(self) -> None:
        verifier = CrossSourceVerifier(rule_engine=None)

        class _Ctx:
            target_tables: list[str] = ["users"]
            action: str = "create"

        result = await verifier.verify({}, _Ctx())
        assert result.passed is True
        assert result.violations == []

    @pytest.mark.asyncio
    async def test_verify_with_rule_engine_pass(self) -> None:
        class _MockRule:
            description: str = "Rule A"

            def check(self, output: dict, constraints: dict) -> bool:
                return True

        class _MockRuleEngine:
            def get_rules(self, action: str) -> list:
                return [_MockRule()]

        verifier = CrossSourceVerifier(rule_engine=_MockRuleEngine())

        class _Ctx:
            target_tables: list[str] = []
            action: str = "test"

        result = await verifier.verify({"data": 1}, _Ctx())
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_verify_with_rule_engine_violation(self) -> None:
        class _MockRule:
            description: str = "Rule B"

            def check(self, output: dict, constraints: dict) -> bool:
                return False

        class _MockRuleEngine:
            def get_rules(self, action: str) -> list:
                return [_MockRule()]

        verifier = CrossSourceVerifier(rule_engine=_MockRuleEngine())

        class _Ctx:
            target_tables: list[str] = []
            action: str = "test"

        result = await verifier.verify({"data": 1}, _Ctx())
        assert result.passed is False
        assert len(result.violations) == 1
        assert "Rule B" in result.violations[0]


class TestExtractFieldReferences:
    """API 字段引用提取测试。"""

    def test_extract_dot_notation(self) -> None:
        """从点号语法中提取字段引用。"""
        tb = TrustBoundary()
        output = {"code": "user_api.email = 'test@example.com'"}
        refs = tb._extract_field_references(output)
        # 应该提取出 user_api.email
        found = any(r.api_name == "user_api" and r.field == "email" for r in refs)
        assert found, f"Expected user_api.email in {[(r.api_name, r.field) for r in refs]}"

    def test_extract_bracket_double_quote(self) -> None:
        """从方括号语法（双引号）中提取字段引用。"""
        tb = TrustBoundary()
        output = {"code": 'user_api["name"] = "test"'}
        refs = tb._extract_field_references(output)
        found = any(r.api_name == "user_api" and r.field == "name" for r in refs)
        assert found, f"Expected user_api.name in {[(r.api_name, r.field) for r in refs]}"

    def test_extract_bracket_single_quote(self) -> None:
        """从方括号语法（单引号）中提取字段引用。"""
        tb = TrustBoundary()
        output = {"code": "order_api['status'] = 'cancelled'"}
        refs = tb._extract_field_references(output)
        found = any(r.api_name == "order_api" and r.field == "status" for r in refs)
        assert found, f"Expected order_api.status in {[(r.api_name, r.field) for r in refs]}"

    def test_extract_multiple_references(self) -> None:
        """从输出中提取多个字段引用。"""
        tb = TrustBoundary()
        output = {"code": "user_api.name and user_api.email and order_api.status"}
        refs = tb._extract_field_references(output)
        api_fields = {(r.api_name, r.field) for r in refs}
        assert ("user_api", "name") in api_fields
        assert ("user_api", "email") in api_fields
        assert ("order_api", "status") in api_fields

    def test_extract_from_nested_dict(self) -> None:
        """从嵌套 dict 中提取字段引用。"""
        tb = TrustBoundary()
        output = {
            "analysis": {
                "sql": "SELECT user_api.age FROM users",
            },
            "notes": "check user_api.email for validity",
        }
        refs = tb._extract_field_references(output)
        api_fields = {(r.api_name, r.field) for r in refs}
        assert ("user_api", "age") in api_fields
        assert ("user_api", "email") in api_fields

    def test_extract_no_references(self) -> None:
        """没有字段引用时返回空列表。"""
        tb = TrustBoundary()
        output = {"message": "everything looks good"}
        refs = tb._extract_field_references(output)
        assert refs == []

    def test_extract_excludes_common_prefixes(self) -> None:
        """排除常见的非 API 引用（http、self 等）。"""
        tb = TrustBoundary()
        output = {"code": "http.url and self.value should not match"}
        refs = tb._extract_field_references(output)
        api_fields = {(r.api_name, r.field) for r in refs}
        assert ("http", "url") not in api_fields
        assert ("self", "value") not in api_fields

    def test_extract_returns_field_ref_objects(self) -> None:
        """返回的对象应包含 api_name 和 field 属性。"""
        tb = TrustBoundary()
        output = {"code": "user_api.email"}
        refs = tb._extract_field_references(output)
        assert len(refs) > 0
        ref = refs[0]
        assert hasattr(ref, "api_name")
        assert hasattr(ref, "field")
        assert ref.api_name == "user_api"
        assert ref.field == "email"

    def test_validate_with_field_references(self) -> None:
        """validate 应检测未知字段引用。"""
        schema = {"user_api": ["id", "name", "email"]}
        tb = TrustBoundary(api_schema=schema)
        output = {"code": "user_api.email and user_api.unknown_field"}
        result = tb.validate(output, {})
        assert result.passed is False
        assert any("unknown_field" in err for err in result.errors)

    def test_validate_with_known_field_references(self) -> None:
        """validate 应通过已知字段引用。"""
        schema = {"user_api": ["id", "name", "email"]}
        tb = TrustBoundary(api_schema=schema)
        output = {"code": "user_api.email and user_api.name"}
        result = tb.validate(output, {})
        assert result.passed is True


class TestCrossSourceVerifierSchemaDict:
    """CrossSourceVerifier schema_dict 功能测试。"""

    @pytest.mark.asyncio
    async def test_load_schema_constraints_with_dict(self) -> None:
        """传入 schema_dict 时应返回对应约束。"""
        schema_dict = {
            "users": {"id": {"type": "integer", "nullable": False}},
            "orders": {"status": {"type": "varchar", "nullable": False}},
        }
        verifier = CrossSourceVerifier(schema_dict=schema_dict)
        constraints = await verifier._load_schema_constraints(["users"])
        assert "users" in constraints
        assert "id" in constraints["users"]

    @pytest.mark.asyncio
    async def test_load_schema_constraints_multiple_tables(self) -> None:
        """同时查询多个表的约束。"""
        schema_dict = {
            "users": {"id": {"type": "integer"}},
            "orders": {"status": {"type": "varchar"}},
        }
        verifier = CrossSourceVerifier(schema_dict=schema_dict)
        constraints = await verifier._load_schema_constraints(["users", "orders"])
        assert "users" in constraints
        assert "orders" in constraints
        assert "id" in constraints["users"]
        assert "status" in constraints["orders"]

    @pytest.mark.asyncio
    async def test_load_schema_constraints_empty_dict(self) -> None:
        """未传入 schema_dict 时返回空字典。"""
        verifier = CrossSourceVerifier()
        constraints = await verifier._load_schema_constraints(["users"])
        assert constraints == {}

    @pytest.mark.asyncio
    async def test_load_schema_constraints_table_not_found(self) -> None:
        """查询不存在的表时该表不出现在结果中。"""
        schema_dict = {"users": {"id": {"type": "integer"}}}
        verifier = CrossSourceVerifier(schema_dict=schema_dict)
        constraints = await verifier._load_schema_constraints(["unknown_table"])
        assert "unknown_table" not in constraints

    @pytest.mark.asyncio
    async def test_load_schema_constraints_case_insensitive(self) -> None:
        """表名查找应大小写不敏感。"""
        schema_dict = {"Users": {"id": {"type": "integer"}}}
        verifier = CrossSourceVerifier(schema_dict=schema_dict)
        constraints = await verifier._load_schema_constraints(["users"])
        assert "users" in constraints

    @pytest.mark.asyncio
    async def test_load_schema_constraints_empty_tables(self) -> None:
        """空表名列表返回空字典。"""
        verifier = CrossSourceVerifier(schema_dict={"users": {}})
        constraints = await verifier._load_schema_constraints([])
        assert constraints == {}

    @pytest.mark.asyncio
    async def test_verify_with_schema_dict_pass(self) -> None:
        """verify 在有 schema_dict 且规则通过时返回 passed=True。"""
        schema_dict = {"users": {"id": {"type": "integer", "nullable": False}}}

        class _MockRule:
            description: str = "id must be non-null"

            def check(self, output: dict, constraints: dict) -> bool:
                # 检查 output 中是否有 id 字段
                return "id" in output

        class _MockRuleEngine:
            def get_rules(self, action: str) -> list:
                return [_MockRule()]

        verifier = CrossSourceVerifier(
            rule_engine=_MockRuleEngine(),
            schema_dict=schema_dict,
        )

        class _Ctx:
            target_tables: list[str] = ["users"]
            action: str = "create"

        result = await verifier.verify({"id": 1}, _Ctx())
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_verify_with_schema_dict_violation(self) -> None:
        """verify 在规则违反时返回 passed=False。"""
        schema_dict = {"users": {"id": {"type": "integer", "nullable": False}}}

        class _MockRule:
            description: str = "id must be non-null"

            def check(self, output: dict, constraints: dict) -> bool:
                return False

        class _MockRuleEngine:
            def get_rules(self, action: str) -> list:
                return [_MockRule()]

        verifier = CrossSourceVerifier(
            rule_engine=_MockRuleEngine(),
            schema_dict=schema_dict,
        )

        class _Ctx:
            target_tables: list[str] = ["users"]
            action: str = "create"

        result = await verifier.verify({"id": 1}, _Ctx())
        assert result.passed is False
        assert len(result.violations) == 1
