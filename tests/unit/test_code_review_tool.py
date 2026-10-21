"""CodeReviewTool 单元测试 — AST 静态分析。

测试要点：
- 正常代码分析（无问题）
- 高复杂度函数检测
- 长函数检测
- 深嵌套检测
- 语法错误处理
- schema 验证
- 空代码处理
"""

from __future__ import annotations

from typing import Any

import pytest

from agentforge.tools.code_review_tool import CodeReviewTool

# 辅助函数


def _find_by_rule(
    findings: list[dict[str, Any]],
    rule: str,
) -> dict[str, Any] | None:
    """查找由规则。

    Args:
        findings: 输入参数。
        rule: 规则。

    Returns:
        结构化结果字典。
    """
    for f in findings:
        if f["rule"] == rule:
            return f
    return None


# 基础测试


class TestCodeReviewToolBasic:
    """CodeReviewTool 基础属性测试。"""

    def test_name(self) -> None:
        """验证名称对应的测试场景。"""
        tool = CodeReviewTool()
        assert tool.name == "code_review"

    def test_schema(self) -> None:
        """验证结构对应的测试场景。"""
        tool = CodeReviewTool()
        schema = tool.schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "code_review"
        props = schema["function"]["parameters"]["properties"]
        assert "file_path" in props
        assert "code_content" in props
        assert "review_types" in props
        required = schema["function"]["parameters"]["required"]
        assert "file_path" in required

    def test_init_defaults(self) -> None:
        """验证初始化默认项对应的测试场景。"""
        tool = CodeReviewTool()
        assert tool.rules_path is None
        assert tool.max_file_size == 1024 * 1024

    def test_init_custom(self) -> None:
        """验证初始化自定义对应的测试场景。"""
        tool = CodeReviewTool(rules_path="/custom/rules", max_file_size=2048)
        assert tool.rules_path == "/custom/rules"
        assert tool.max_file_size == 2048

    def test_thresholds(self) -> None:
        """验证阈值对应的测试场景。"""
        assert CodeReviewTool.MAX_COMPLEXITY == 10
        assert CodeReviewTool.MAX_FUNCTION_LENGTH == 50
        assert CodeReviewTool.MAX_NESTING_DEPTH == 4


# 正常代码分析（无问题）


class TestCodeReviewCleanCode:
    """正常代码分析 — 无问题检测。"""

    @pytest.mark.asyncio
    async def test_simple_function_no_issues(self) -> None:
        """简单函数不应报告任何问题。"""
        code = "def add(a, b):\n    return a + b\n"
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        assert result.success is True
        assert result.metadata["findings"] == []
        assert result.metadata["severity"] == "info"

    @pytest.mark.asyncio
    async def test_multiple_clean_functions(self) -> None:
        """多个简单函数都不应有问题。"""
        code = (
            "def func_a():\n"
            "    return 1\n"
            "\n"
            "def func_b(x):\n"
            "    if x:\n"
            "        return x\n"
            "    return 0\n"
        )
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        assert result.success is True
        assert result.metadata["findings"] == []

    @pytest.mark.asyncio
    async def test_moderate_complexity_no_warning(self) -> None:
        """验证复杂度无警告对应的测试场景。"""
        # 复杂度 = 1（基础） + 9（分支） = 10，不超过 10
        code = (
            "def func(x):\n"
            "    if x == 1:\n"
            "        pass\n"
            "    elif x == 2:\n"
            "        pass\n"
            "    elif x == 3:\n"
            "        pass\n"
            "    elif x == 4:\n"
            "        pass\n"
            "    elif x == 5:\n"
            "        pass\n"
            "    elif x == 6:\n"
            "        pass\n"
            "    elif x == 7:\n"
            "        pass\n"
            "    elif x == 8:\n"
            "        pass\n"
            "    elif x == 9:\n"
            "        pass\n"
            "    return x\n"
        )
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        assert result.success is True
        finding = _find_by_rule(result.metadata["findings"], "high_complexity")
        assert finding is None

    @pytest.mark.asyncio
    async def test_output_contains_summary(self) -> None:
        """输出字符串包含汇总信息。"""
        code = "def add(a, b):\n    return a + b\n"
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        assert "Code review completed" in result.output
        assert "0 issues" in result.output


# 高复杂度函数检测


class TestCodeReviewHighComplexity:
    """高复杂度函数检测。"""

    @pytest.mark.asyncio
    async def test_high_complexity_detected(self) -> None:
        """复杂度超过 10 的函数应被标记。"""
        # 复杂度 = 1 + 11 = 12
        code = (
            "def complex_func(x):\n"
            "    if x == 1:\n"
            "        pass\n"
            "    elif x == 2:\n"
            "        pass\n"
            "    elif x == 3:\n"
            "        pass\n"
            "    elif x == 4:\n"
            "        pass\n"
            "    elif x == 5:\n"
            "        pass\n"
            "    elif x == 6:\n"
            "        pass\n"
            "    elif x == 7:\n"
            "        pass\n"
            "    elif x == 8:\n"
            "        pass\n"
            "    elif x == 9:\n"
            "        pass\n"
            "    elif x == 10:\n"
            "        pass\n"
            "    elif x == 11:\n"
            "        pass\n"
            "    return x\n"
        )
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        assert result.success is True
        finding = _find_by_rule(result.metadata["findings"], "high_complexity")
        assert finding is not None
        assert finding["severity"] == "warning"
        assert "complex_func" in finding["description"]
        assert finding["line"] == 1

    @pytest.mark.asyncio
    async def test_complexity_with_loops_and_boolops(self) -> None:
        """验证复杂度使用及布尔运算对应的测试场景。"""
        code = (
            "def func(data):\n"
            "    for item in data:\n"
            "        if item and item.value:\n"
            "            while item.next:\n"
            "                try:\n"
            "                    process(item)\n"
            "                except ValueError:\n"
            "                    pass\n"
            "                except TypeError:\n"
            "                    pass\n"
            "    return data\n"
        )
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        # 复杂度 = 1 + for(1) + if(1) + boolop(1) + while(1) + try无(0)
        # + except(2) = 7，不超过 10
        finding = _find_by_rule(result.metadata["findings"], "high_complexity")
        assert finding is None

    @pytest.mark.asyncio
    async def test_complexity_with_many_boolops(self) -> None:
        """验证复杂度使用布尔运算对应的测试场景。"""
        code = (
            "def func(a, b, c, d, e, f, g, h, i, j, k):\n"
            "    if a and b or c and d or e and f or g and h or i and j or k:\n"
            "        return True\n"
            "    return False\n"
        )
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        # 复杂度 = 1 + if(1) + boolops(6) = 8，不超过 10
        finding = _find_by_rule(result.metadata["findings"], "high_complexity")
        assert finding is None

    @pytest.mark.asyncio
    async def test_severity_is_warning_for_high_complexity(self) -> None:
        """验证严重性是否警告用于高复杂度对应的测试场景。"""
        code = (
            "def f():\n"
            "    if 1:\n"
            "        pass\n"
            "    if 2:\n"
            "        pass\n"
            "    if 3:\n"
            "        pass\n"
            "    if 4:\n"
            "        pass\n"
            "    if 5:\n"
            "        pass\n"
            "    if 6:\n"
            "        pass\n"
            "    if 7:\n"
            "        pass\n"
            "    if 8:\n"
            "        pass\n"
            "    if 9:\n"
            "        pass\n"
            "    if 10:\n"
            "        pass\n"
            "    if 11:\n"
            "        pass\n"
        )
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        assert result.metadata["severity"] == "warning"
        assert result.metadata["warning_count"] > 0


# 长函数检测


class TestCodeReviewLongFunction:
    """长函数检测。"""

    @pytest.mark.asyncio
    async def test_long_function_detected(self) -> None:
        """超过 50 行的函数应被标记。"""
        lines = ["def long_func():"]
        for i in range(55):
            lines.append(f"    x = {i}")
        lines.append("    return x")
        code = "\n".join(lines) + "\n"

        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        assert result.success is True
        finding = _find_by_rule(result.metadata["findings"], "long_function")
        assert finding is not None
        assert finding["severity"] == "warning"
        assert "long_func" in finding["description"]

    @pytest.mark.asyncio
    async def test_short_function_not_flagged(self) -> None:
        """50 行以内的函数不应被标记。"""
        lines = ["def short_func():"]
        for i in range(45):
            lines.append(f"    x = {i}")
        lines.append("    return x")
        code = "\n".join(lines) + "\n"

        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        finding = _find_by_rule(result.metadata["findings"], "long_function")
        assert finding is None

    @pytest.mark.asyncio
    async def test_boundary_50_lines_not_flagged(self) -> None:
        """恰好 50 行的函数不应被标记（阈值是 >50）。"""
        lines = ["def boundary_func():"]
        for i in range(48):
            lines.append(f"    x = {i}")
        lines.append("    return x")
        code = "\n".join(lines) + "\n"
        # 总共 50 行

        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        finding = _find_by_rule(result.metadata["findings"], "long_function")
        assert finding is None


# 深嵌套检测


class TestCodeReviewDeepNesting:
    """深嵌套检测。"""

    @pytest.mark.asyncio
    async def test_deep_nesting_detected(self) -> None:
        """嵌套深度超过 4 层应被标记。"""
        code = (
            "def deep_func():\n"
            "    if a:\n"
            "        if b:\n"
            "            if c:\n"
            "                if d:\n"
            "                    if e:\n"
            "                        pass\n"
        )
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        assert result.success is True
        finding = _find_by_rule(result.metadata["findings"], "deep_nesting")
        assert finding is not None
        assert finding["severity"] == "warning"
        assert "deep_func" in finding["description"]

    @pytest.mark.asyncio
    async def test_normal_nesting_not_flagged(self) -> None:
        """嵌套深度恰好 4 层不应被标记。"""
        code = (
            "def normal_func():\n"
            "    if a:\n"
            "        if b:\n"
            "            if c:\n"
            "                if d:\n"
            "                    pass\n"
        )
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        finding = _find_by_rule(result.metadata["findings"], "deep_nesting")
        assert finding is None

    @pytest.mark.asyncio
    async def test_nesting_with_mixed_structures(self) -> None:
        """验证使用对应的测试场景。"""
        code = (
            "def mixed_func():\n"
            "    if a:\n"
            "        for x in y:\n"
            "            while z:\n"
            "                if w:\n"
            "                    if v:\n"
            "                        pass\n"
        )
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        finding = _find_by_rule(result.metadata["findings"], "deep_nesting")
        assert finding is not None
        assert "nesting depth of 5" in finding["description"]


# 语法错误处理


class TestCodeReviewSyntaxError:
    """语法错误处理。"""

    @pytest.mark.asyncio
    async def test_syntax_error_returns_failure(self) -> None:
        """验证语法错误返回失败对应的测试场景。"""
        code = "def broken_func(\n    # missing closing paren\n"
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        assert result.success is False
        assert result.error is not None
        assert "SyntaxError" in result.error

    @pytest.mark.asyncio
    async def test_syntax_error_metadata(self) -> None:
        """验证语法错误元数据对应的测试场景。"""
        code = "def broken(:\n    pass\n"
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        assert "syntax_error" in result.metadata
        assert result.metadata["syntax_error"]["line"] is not None
        assert result.metadata["findings"] == []

    @pytest.mark.asyncio
    async def test_syntax_error_output_message(self) -> None:
        """输出字符串应提及语法错误。"""
        code = "x = \n"
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        assert "syntax error" in result.output.lower()


# 空代码处理


class TestCodeReviewEmptyCode:
    """空代码处理。"""

    @pytest.mark.asyncio
    async def test_empty_code(self) -> None:
        """验证空代码对应的测试场景。"""
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content="",
        )
        assert result.success is True
        assert result.metadata["findings"] == []

    @pytest.mark.asyncio
    async def test_whitespace_only_code(self) -> None:
        """只有空白字符的代码应视为空。"""
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content="   \n   \n   ",
        )
        assert result.success is True
        assert result.metadata["findings"] == []

    @pytest.mark.asyncio
    async def test_no_code_content_provided(self) -> None:
        """验证无代码内容对应的测试场景。"""
        tool = CodeReviewTool()
        result = await tool.execute(file_path="test.py")
        assert result.success is True
        assert result.metadata["findings"] == []


# 综合测试


class TestCodeReviewComprehensive:
    """综合场景测试。"""

    @pytest.mark.asyncio
    async def test_multiple_issues_in_one_function(self) -> None:
        """一个函数同时触发多个规则。"""
        # 高复杂度 + 深嵌套
        lines = ["def problematic(x):"]
        for i in range(15):
            lines.append(f"    if x == {i}:")
            lines.append("        pass")
        lines.append("    return x")
        code = "\n".join(lines) + "\n"

        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        assert result.success is True
        rules = {f["rule"] for f in result.metadata["findings"]}
        assert "high_complexity" in rules

    @pytest.mark.asyncio
    async def test_multiple_functions_independent(self) -> None:
        """多个函数的问题应独立检测。"""
        code = "def clean_func():\n" "    return 1\n" "\n"
        # 添加一个高复杂度函数
        code += "def complex_func(x):\n"
        for i in range(12):
            code += f"    if x == {i}:\n"
            code += "        pass\n"
        code += "    return x\n"

        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        assert result.success is True
        finding = _find_by_rule(result.metadata["findings"], "high_complexity")
        assert finding is not None
        assert "complex_func" in finding["description"]
        assert "clean_func" not in finding["description"]

    @pytest.mark.asyncio
    async def test_async_function_analyzed(self) -> None:
        """验证异步函数对应的测试场景。"""
        code = (
            "async def async_func():\n"
            "    for i in range(100):\n"
            "        for j in range(100):\n"
            "            for k in range(100):\n"
            "                for l in range(100):\n"
            "                    for m in range(100):\n"
            "                        pass\n"
        )
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        assert result.success is True
        finding = _find_by_rule(result.metadata["findings"], "deep_nesting")
        assert finding is not None
        assert "async_func" in finding["description"]

    @pytest.mark.asyncio
    async def test_class_methods_analyzed(self) -> None:
        """类方法也应被分析。"""
        code = (
            "class MyClass:\n"
            "    def method_a(self):\n"
            "        return 1\n"
            "\n"
            "    def method_b(self, x):\n"
        )
        for i in range(12):
            code += f"        if x == {i}:\n"
            code += "            pass\n"
        code += "        return x\n"

        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        assert result.success is True
        finding = _find_by_rule(result.metadata["findings"], "high_complexity")
        assert finding is not None
        assert "method_b" in finding["description"]

    @pytest.mark.asyncio
    async def test_review_types_in_metadata(self) -> None:
        """验证审核在元数据对应的测试场景。"""
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content="def f():\n    pass\n",
            review_types=["security"],
        )
        assert result.metadata["review_types"] == ["security"]

    @pytest.mark.asyncio
    async def test_finding_has_all_fields(self) -> None:
        """验证具有全部字段对应的测试场景。"""
        code = (
            "def f():\n"
            "    if 1:\n"
            "        if 2:\n"
            "            if 3:\n"
            "                if 4:\n"
            "                    if 5:\n"
            "                        pass\n"
        )
        tool = CodeReviewTool()
        result = await tool.execute(
            file_path="test.py",
            code_content=code,
        )
        for finding in result.metadata["findings"]:
            assert "rule" in finding
            assert "severity" in finding
            assert "description" in finding
            assert "line" in finding
