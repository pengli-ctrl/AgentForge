"""测试执行工具模块。"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from agentforge.core.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class TestExecutionTool(BaseTool):
    """测试执行工具 — 运行单元测试并分析结果。"""

    def __init__(self, timeout: int = 300) -> None:
        """初始化 TestExecutionTool。

        Args:
            timeout: 操作超时时间。
        """
        self.timeout = timeout

    __test__ = False

    @property
    def name(self) -> str:
        """工具唯一标识。

        Returns:
            字符串结果。
        """
        return "test_execution"

    def schema(self) -> dict:
        """返回工具参数的结构定义。

        Returns:
            结构化结果字典。
        """
        return {
            "type": "function",
            "function": {
                "name": "test_execution",
                "description": "执行单元测试并分析结果",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "test_path": {
                            "type": "string",
                            "description": "测试文件或目录路径",
                        },
                        "test_command": {
                            "type": "string",
                            "description": "自定义测试命令（可选）",
                        },
                        "coverage": {
                            "type": "boolean",
                            "description": "是否收集覆盖率",
                            "default": True,
                        },
                    },
                    "required": ["test_path"],
                },
            },
        }

    @staticmethod
    def _parse_output(output: str) -> dict[str, Any]:
        """解析输出。

        Args:
            output: 输出。

        Returns:
            结构化结果字典。
        """
        result: dict[str, Any] = {
            "passed": 0,
            "failed": 0,
            "total": 0,
            "coverage": None,
        }

        # 提取通过数
        passed_match = re.search(r"(\d+)\s+passed", output)
        if passed_match:
            result["passed"] = int(passed_match.group(1))

        # 提取失败数
        failed_match = re.search(r"(\d+)\s+failed", output)
        if failed_match:
            result["failed"] = int(failed_match.group(1))

        # 提取覆盖率
        coverage_match = re.search(
            r"(?:TOTAL|total).*?(\d+(?:\.\d+)?)\s*%",
            output,
        )
        if coverage_match:
            result["coverage"] = float(coverage_match.group(1))
        else:
            # 兼容其他覆盖率输出格式
            coverage_match2 = re.search(r"(\d+(?:\.\d+)?)\%\s*coverage", output)
            if coverage_match2:
                result["coverage"] = float(coverage_match2.group(1))

        result["total"] = result["passed"] + result["failed"]

        return result

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行核心处理逻辑并返回结果。

        Args:
            kwargs: 关键字参数。

        Returns:
            工具结果结果。
        """
        test_path = kwargs.get("test_path", "")
        test_command = kwargs.get("test_command", "")
        coverage = kwargs.get("coverage", True)

        logger.info(
            "Test execution started (path=%s, coverage=%s)",
            test_path,
            coverage,
        )

        # 构建命令
        if test_command:
            cmd = test_command.split()
        else:
            cmd = [
                "python",
                "-m",
                "pytest",
                test_path,
                "-v",
                "--tb=short",
            ]

        logger.info("Executing test command: %s", " ".join(cmd))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output="",
                error="Test executable not found. " "Please ensure pytest is installed.",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to execute test command: {e}",
            )

        # 等待进程完成，支持超时
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            logger.warning(
                "Test execution timed out after %ds (path=%s)",
                self.timeout,
                test_path,
            )
            return ToolResult(
                success=False,
                output=f"Test execution timed out after " f"{self.timeout}s for {test_path}.",
                error=f"TimeoutError: test execution exceeded " f"{self.timeout}s timeout",
                metadata={
                    "test_path": test_path,
                    "timed_out": True,
                    "passed": 0,
                    "failed": 0,
                    "total": 0,
                    "coverage": None,
                },
            )

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        combined_output = stdout_text + "\n" + stderr_text

        # 解析输出
        parsed = self._parse_output(combined_output)

        passed = parsed["passed"]
        failed = parsed["failed"]
        total = parsed["total"]
        cov = parsed["coverage"]

        success = failed == 0 and process.returncode == 0

        logger.info(
            "Test execution completed (path=%s, passed=%d, failed=%d, " "coverage=%s, success=%s)",
            test_path,
            passed,
            failed,
            cov,
            success,
        )

        output = (
            f"Test execution completed for {test_path}. "
            f"Passed: {passed}, Failed: {failed}, Total: {total}."
        )
        if cov is not None:
            output += f" Coverage: {cov}%."

        metadata: dict[str, Any] = {
            "test_path": test_path,
            "passed": passed,
            "failed": failed,
            "total": total,
            "coverage": cov,
            "returncode": process.returncode,
        }
        if not success and failed == 0:
            # 执行失败但没有明确的失败测试（可能是收集错误）
            metadata["stderr"] = stderr_text[:500]

        return ToolResult(
            success=success,
            output=output,
            error=stderr_text.strip() if not success else None,
            metadata=metadata,
        )
