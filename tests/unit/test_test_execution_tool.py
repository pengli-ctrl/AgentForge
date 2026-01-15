"""TestExecutionTool 单元测试 — subprocess 执行 + 输出解析。

测试要点：
- 成功执行（Mock subprocess 返回 passed=5, failed=0）
- 测试失败（Mock subprocess 返回 passed=3, failed=2）
- 超时处理
- 自定义命令
- schema 验证
- 输出解析
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentforge.tools.test_execution_tool import TestExecutionTool

# 说明：该步骤用于实现上述逻辑并保证行为稳定。
# 辅助函数 — mock asyncio.create_subprocess_exec
# 说明：该步骤用于实现上述逻辑并保证行为稳定。


def _make_mock_process(
    stdout: bytes = b"",
    stderr: bytes = b"",
    returncode: int = 0,
):
    """创建 mock 的 asyncio 子进程对象。

    Args:
        stdout: 标准输出内容。
        stderr: 标准错误内容。
        returncode: 退出码。

    Returns:
        MagicMock 模拟的 Process 对象。
    """
    process = MagicMock()
    process.communicate = AsyncMock(return_value=(stdout, stderr))
    process.returncode = returncode
    return process


# 说明：该步骤用于实现上述逻辑并保证行为稳定。
# 基础测试
# 说明：该步骤用于实现上述逻辑并保证行为稳定。


class TestTestExecutionToolBasic:
    """TestExecutionTool 基础属性测试。"""

    def test_name(self) -> None:
        """验证 name 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        tool = TestExecutionTool()
        assert tool.name == "test_execution"

    def test_schema(self) -> None:
        """验证 schema 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        tool = TestExecutionTool()
        schema = tool.schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "test_execution"
        props = schema["function"]["parameters"]["properties"]
        assert "test_path" in props
        assert "test_command" in props
        assert "coverage" in props
        required = schema["function"]["parameters"]["required"]
        assert "test_path" in required

    def test_init_defaults(self) -> None:
        """验证 init_defaults 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        tool = TestExecutionTool()
        assert tool.timeout == 300

    def test_init_custom_timeout(self) -> None:
        """验证 init_custom_timeout 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        tool = TestExecutionTool(timeout=60)
        assert tool.timeout == 60


# 说明：该步骤用于实现上述逻辑并保证行为稳定。
# 成功执行测试
# 说明：该步骤用于实现上述逻辑并保证行为稳定。


class TestTestExecutionSuccess:
    """测试成功执行场景。"""

    @pytest.mark.asyncio
    async def test_all_tests_pass(self) -> None:
        """所有测试通过时应返回 success=True。"""
        stdout = b"===== 5 passed in 2.5s =====\n"
        mock_process = _make_mock_process(stdout=stdout, returncode=0)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            tool = TestExecutionTool()
            result = await tool.execute(test_path="tests/")

        assert result.success is True
        assert result.metadata["passed"] == 5
        assert result.metadata["failed"] == 0
        assert result.metadata["total"] == 5
        assert result.error is None

    @pytest.mark.asyncio
    async def test_pass_count_in_output(self) -> None:
        """输出字符串应包含通过数。"""
        stdout = b"3 passed in 1.0s\n"
        mock_process = _make_mock_process(stdout=stdout, returncode=0)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            tool = TestExecutionTool()
            result = await tool.execute(test_path="tests/")

        assert "Passed: 3" in result.output

    @pytest.mark.asyncio
    async def test_coverage_extracted(self) -> None:
        """覆盖率应从输出中提取。"""
        stdout = (
            b"5 passed in 2.0s\n"
            b"Name             Stmts   Miss  Cover\n"
            b"------------------------------------\n"
            b"module.py           50      5    90%\n"
            b"------------------------------------\n"
            b"TOTAL              100     10    90%\n"
        )
        mock_process = _make_mock_process(stdout=stdout, returncode=0)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            tool = TestExecutionTool()
            result = await tool.execute(test_path="tests/")

        assert result.metadata["coverage"] == 90.0
        assert "Coverage: 90.0%" in result.output

    @pytest.mark.asyncio
    async def test_no_tests_collected(self) -> None:
        """没有测试时不应崩溃。"""
        stdout = b"no tests ran in 0.0s\n"
        mock_process = _make_mock_process(stdout=stdout, returncode=0)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            tool = TestExecutionTool()
            result = await tool.execute(test_path="tests/")

        assert result.metadata["passed"] == 0
        assert result.metadata["failed"] == 0
        assert result.metadata["total"] == 0


# 说明：该步骤用于实现上述逻辑并保证行为稳定。
# 测试失败场景
# 说明：该步骤用于实现上述逻辑并保证行为稳定。


class TestTestExecutionFailure:
    """测试失败执行场景。"""

    @pytest.mark.asyncio
    async def test_some_tests_fail(self) -> None:
        """部分测试失败时应返回 success=False。"""
        stdout = b"===== 3 passed, 2 failed in 3.0s =====\n"
        stderr = b"FAILED test_a - AssertionError\nFAILED test_b - KeyError\n"
        mock_process = _make_mock_process(stdout=stdout, stderr=stderr, returncode=1)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            tool = TestExecutionTool()
            result = await tool.execute(test_path="tests/")

        assert result.success is False
        assert result.metadata["passed"] == 3
        assert result.metadata["failed"] == 2
        assert result.metadata["total"] == 5

    @pytest.mark.asyncio
    async def test_fail_count_in_output(self) -> None:
        """输出字符串应包含失败数。"""
        stdout = b"1 passed, 2 failed in 1.0s\n"
        mock_process = _make_mock_process(stdout=stdout, returncode=1)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            tool = TestExecutionTool()
            result = await tool.execute(test_path="tests/")

        assert "Failed: 2" in result.output

    @pytest.mark.asyncio
    async def test_all_tests_fail(self) -> None:
        """所有测试失败时应返回 success=False。"""
        stdout = b"===== 3 failed in 2.0s =====\n"
        mock_process = _make_mock_process(stdout=stdout, returncode=1)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            tool = TestExecutionTool()
            result = await tool.execute(test_path="tests/")

        assert result.success is False
        assert result.metadata["passed"] == 0
        assert result.metadata["failed"] == 3


# 说明：该步骤用于实现上述逻辑并保证行为稳定。
# 超时处理
# 说明：该步骤用于实现上述逻辑并保证行为稳定。


class TestTestExecutionTimeout:
    """超时处理测试。"""

    @pytest.mark.asyncio
    async def test_timeout_returns_failure(self) -> None:
        """超时应返回 success=False。"""
        mock_process = MagicMock()
        mock_process.communicate = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.returncode = None

        with (
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ),
            patch(
                "asyncio.wait_for",
                side_effect=asyncio.TimeoutError(),
            ),
        ):
            tool = TestExecutionTool(timeout=5)
            result = await tool.execute(test_path="tests/")

        assert result.success is False
        assert result.metadata["timed_out"] is True
        assert "timed out" in result.output.lower()

    @pytest.mark.asyncio
    async def test_timeout_metadata(self) -> None:
        """超时元数据应正确。"""
        mock_process = MagicMock()
        mock_process.kill = MagicMock()

        with (
            patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ),
            patch(
                "asyncio.wait_for",
                side_effect=asyncio.TimeoutError(),
            ),
        ):
            tool = TestExecutionTool(timeout=10)
            result = await tool.execute(test_path="tests/")

        assert result.metadata["passed"] == 0
        assert result.metadata["failed"] == 0
        assert result.metadata["total"] == 0
        assert result.metadata["coverage"] is None


# 说明：该步骤用于实现上述逻辑并保证行为稳定。
# 自定义命令
# 说明：该步骤用于实现上述逻辑并保证行为稳定。


class TestTestExecutionCustomCommand:
    """自定义命令测试。"""

    @pytest.mark.asyncio
    async def test_custom_command_used(self) -> None:
        """应使用自定义命令而非默认 pytest 命令。"""
        stdout = b"2 passed in 1.0s\n"
        mock_process = _make_mock_process(stdout=stdout, returncode=0)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ) as mock_exec:
            tool = TestExecutionTool()
            result = await tool.execute(
                test_path="tests/",
                test_command="python -m pytest tests/ -x --tb=long",
            )

        assert result.success is True
        # 验证传入 create_subprocess_exec 的第一个参数是 python
        call_args = mock_exec.call_args
        args = call_args[0]
        assert args[0] == "python"
        assert "-x" in args
        assert "--tb=long" in args

    @pytest.mark.asyncio
    async def test_default_command_when_no_custom(self) -> None:
        """无自定义命令时应使用默认 pytest 命令。"""
        stdout = b"1 passed in 0.5s\n"
        mock_process = _make_mock_process(stdout=stdout, returncode=0)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ) as mock_exec:
            tool = TestExecutionTool()
            result = await tool.execute(test_path="tests/unit/")

        assert result.success is True
        call_args = mock_exec.call_args
        args = call_args[0]
        assert args[0] == "python"
        assert "pytest" in args
        assert "tests/unit/" in args
        assert "-v" in args
        assert "--tb=short" in args


# 说明：该步骤用于实现上述逻辑并保证行为稳定。
# 输出解析
# 说明：该步骤用于实现上述逻辑并保证行为稳定。


class TestTestExecutionOutputParsing:
    """输出解析测试。"""

    def test_parse_passed_only(self) -> None:
        """解析只有 passed 的输出。"""
        result = TestExecutionTool._parse_output("10 passed in 5.0s")
        assert result["passed"] == 10
        assert result["failed"] == 0
        assert result["total"] == 10

    def test_parse_passed_and_failed(self) -> None:
        """解析 passed 和 failed 共存的输出。"""
        result = TestExecutionTool._parse_output("3 passed, 2 failed in 3.0s")
        assert result["passed"] == 3
        assert result["failed"] == 2
        assert result["total"] == 5

    def test_parse_failed_only(self) -> None:
        """解析只有 failed 的输出。"""
        result = TestExecutionTool._parse_output("5 failed in 2.0s")
        assert result["passed"] == 0
        assert result["failed"] == 5
        assert result["total"] == 5

    def test_parse_no_results(self) -> None:
        """解析无测试结果的输出。"""
        result = TestExecutionTool._parse_output("no tests ran")
        assert result["passed"] == 0
        assert result["failed"] == 0
        assert result["total"] == 0
        assert result["coverage"] is None

    def test_parse_coverage_total(self) -> None:
        """解析 TOTAL 行的覆盖率。"""
        output = "5 passed in 2.0s\n" "TOTAL    100    10    90%\n"
        result = TestExecutionTool._parse_output(output)
        assert result["coverage"] == 90.0

    def test_parse_coverage_with_decimal(self) -> None:
        """解析带小数的覆盖率。"""
        output = "3 passed in 1.0s\n" "TOTAL    50    5    87.5%\n"
        result = TestExecutionTool._parse_output(output)
        assert result["coverage"] == 87.5

    def test_parse_no_coverage(self) -> None:
        """无覆盖率信息时 coverage 应为 None。"""
        result = TestExecutionTool._parse_output("2 passed in 1.0s")
        assert result["coverage"] is None

    def test_parse_empty_output(self) -> None:
        """空输出应返回全零结果。"""
        result = TestExecutionTool._parse_output("")
        assert result["passed"] == 0
        assert result["failed"] == 0
        assert result["total"] == 0
        assert result["coverage"] is None


# 说明：该步骤用于实现上述逻辑并保证行为稳定。
# 综合测试
# 说明：该步骤用于实现上述逻辑并保证行为稳定。


class TestTestExecutionComprehensive:
    """综合场景测试。"""

    @pytest.mark.asyncio
    async def test_metadata_contains_all_fields(self) -> None:
        """metadata 应包含所有必要字段。"""
        stdout = b"5 passed in 2.0s\n"
        mock_process = _make_mock_process(stdout=stdout, returncode=0)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            tool = TestExecutionTool()
            result = await tool.execute(test_path="tests/")

        assert "test_path" in result.metadata
        assert "passed" in result.metadata
        assert "failed" in result.metadata
        assert "total" in result.metadata
        assert "coverage" in result.metadata
        assert "returncode" in result.metadata

    @pytest.mark.asyncio
    async def test_stderr_in_metadata_on_failure(self) -> None:
        """执行失败且无明确失败数时 stderr 应在 metadata 中。"""
        stdout = b"ERROR: file not found\n"
        stderr = b"collection error\n"
        mock_process = _make_mock_process(stdout=stdout, stderr=stderr, returncode=2)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            tool = TestExecutionTool()
            result = await tool.execute(test_path="nonexistent/")

        assert result.success is False
        assert "stderr" in result.metadata

    @pytest.mark.asyncio
    async def test_executable_not_found(self) -> None:
        """可执行文件不存在时应返回错误。"""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("python not found"),
        ):
            tool = TestExecutionTool()
            result = await tool.execute(test_path="tests/")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_coverage_none_in_output_when_absent(self) -> None:
        """无覆盖率时输出不应包含 Coverage。"""
        stdout = b"3 passed in 1.0s\n"
        mock_process = _make_mock_process(stdout=stdout, returncode=0)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_process,
        ):
            tool = TestExecutionTool()
            result = await tool.execute(test_path="tests/")

        assert "Coverage" not in result.output
