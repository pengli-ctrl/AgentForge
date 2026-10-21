"""Git工具模块。"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from agentforge.core.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class GitTool(BaseTool):
    """Git工具相关组件。

    Attributes:
        ALLOWED_OPS: 允许。
    """

    # 允许的 Git 操作（白名单）
    ALLOWED_OPS: set[str] = {"clone", "pull", "diff", "log", "show", "status"}

    def __init__(
        self,
        workspace: str = "/tmp/agentforge-workspace",
        allowed_repo_urls: set[str] | None = None,
        command_timeout: float = 60.0,
    ) -> None:
        """初始化 GitTool。

        Args:
            workspace: 输入参数。
            allowed_repo_urls: 允许仓储。
            command_timeout: 超时。
        """
        self.workspace = workspace
        self.allowed_repo_urls = allowed_repo_urls or set()
        self._command_timeout = command_timeout

    @property
    def name(self) -> str:
        """工具唯一标识。

        Returns:
            字符串结果。
        """
        return "git"

    def schema(self) -> dict:
        """返回工具参数的结构定义。

        Returns:
            结构化结果字典。
        """
        return {
            "type": "function",
            "function": {
                "name": "git",
                "description": "执行 Git 操作（clone、diff、log 等）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": list(self.ALLOWED_OPS),
                            "description": "Git 操作类型",
                        },
                        "repo_url": {
                            "type": "string",
                            "description": "仓库 URL（clone 操作时需要）",
                        },
                        "branch": {
                            "type": "string",
                            "description": "分支名称（可选）",
                        },
                        "commit_range": {
                            "type": "string",
                            "description": "提交范围（diff 操作时需要，如 main...feature）",
                        },
                    },
                    "required": ["operation"],
                },
            },
        }

    def _validate_local_path(self, local_path: str) -> Path:
        """校验本地路径安全性 — 防止路径遍历攻击。

        Args:
            local_path: 本地路径。

        Returns:
            路径结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        # 检查路径遍历攻击
        if ".." in local_path:
            raise ValueError(f"Path traversal detected: '{local_path}' contains '..'")

        workspace_path = Path(self.workspace).resolve()

        # 处理相对路径和绝对路径
        if os.path.isabs(local_path):
            full_path = Path(local_path).resolve()
        else:
            full_path = (workspace_path / local_path).resolve()

        # 确保路径在 workspace 内
        try:
            full_path.relative_to(workspace_path)
        except ValueError:
            raise ValueError(f"Path '{local_path}' is outside workspace '{self.workspace}'")

        return full_path

    def _validate_repo_url(self, repo_url: str) -> None:
        """校验仓库 URL 是否在白名单中。

        Args:
            repo_url: 仓储URL。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if self.allowed_repo_urls and repo_url not in self.allowed_repo_urls:
            raise ValueError(
                f"Repository URL '{repo_url}' is not in the allowed list. "
                f"Allowed: {self.allowed_repo_urls}"
            )

    async def _run_git_command(self, args: list[str]) -> ToolResult:
        """运行 Git 命令并返回执行结果。

        Args:
            args: 位置参数。

        Returns:
            工具结果结果。
        """
        cmd = ["git"] + args
        logger.info("Executing git command: %s", " ".join(cmd))

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
                error="git executable not found. Please install git.",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to execute git command: {e}",
            )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._command_timeout
            )
        except asyncio.TimeoutError:
            logger.error(
                "Git command timed out after %.0fs, killing process (args=%s)",
                self._command_timeout,
                args,
            )
            await self._kill_process(process)
            return ToolResult(
                success=False,
                output="",
                error=f"git command timed out after {self._command_timeout}s",
            )
        except Exception as e:
            await self._kill_process(process)
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to execute git command: {e}",
            )

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        if process.returncode != 0:
            logger.warning(
                "Git command failed (returncode=%d, args=%s, stderr=%s)",
                process.returncode,
                args,
                stderr_text[:200],
            )
            return ToolResult(
                success=False,
                output=stdout_text,
                error=stderr_text.strip() or f"git exited with code {process.returncode}",
                metadata={"returncode": process.returncode},
            )

        logger.info("Git command succeeded (args=%s, output_len=%d)", args, len(stdout_text))
        return ToolResult(
            success=True,
            output=stdout_text,
            metadata={"returncode": process.returncode},
        )

    async def _kill_process(self, process: asyncio.subprocess.Process) -> None:
        """处理。

        Args:
            process: 处理。
        """
        try:
            process.kill()
        except ProcessLookupError:
            pass
        except Exception:
            logger.debug("process already terminated", exc_info=True)
        try:
            await process.wait()
        except Exception:
            logger.debug("failed to reap process after kill", exc_info=True)

    async def execute(self, **kwargs: Any) -> ToolResult:
        """执行核心处理逻辑并返回结果。

        Args:
            kwargs: 关键字参数。

        Returns:
            工具结果结果。
        """
        operation = kwargs.get("operation", "")

        # 操作白名单校验
        if operation not in self.ALLOWED_OPS:
            return ToolResult(
                success=False,
                output="",
                error=f"Git operation '{operation}' is not allowed. "
                f"Allowed: {self.ALLOWED_OPS}",
            )

        logger.info("Git operation: %s", operation)

        try:
            if operation == "clone":
                return await self._do_clone(kwargs)
            elif operation == "pull":
                return await self._do_pull(kwargs)
            elif operation == "diff":
                return await self._do_diff(kwargs)
            elif operation == "log":
                return await self._do_log(kwargs)
            elif operation == "show":
                return await self._do_show(kwargs)
            elif operation == "status":
                return await self._do_status(kwargs)
        except ValueError as e:
            return ToolResult(success=False, output="", error=str(e))

        # 不应该到达这里
        return ToolResult(success=False, output="", error=f"Unknown operation: {operation}")

    async def _do_clone(self, kwargs: dict[str, Any]) -> ToolResult:
        """执行克隆。

        Args:
            kwargs: 关键字参数。

        Returns:
            工具结果结果。
        """
        repo_url = kwargs.get("repo_url", "")
        local_path = kwargs.get("local_path", "")
        branch = kwargs.get("branch", "")

        if not repo_url:
            return ToolResult(success=False, output="", error="repo_url is required for clone")
        if not local_path:
            return ToolResult(success=False, output="", error="local_path is required for clone")

        # 安全校验
        self._validate_repo_url(repo_url)
        full_path = self._validate_local_path(local_path)

        # 确保父目录存在
        full_path.parent.mkdir(parents=True, exist_ok=True)

        args = ["clone"]
        if branch:
            args.extend(["-b", branch])
        args.extend([repo_url, str(full_path)])

        result = await self._run_git_command(args)
        if result.success:
            result.metadata["operation"] = "clone"
            result.metadata["repo_url"] = repo_url
            result.metadata["local_path"] = str(full_path)
        return result

    async def _do_pull(self, kwargs: dict[str, Any]) -> ToolResult:
        """执行拉取。

        Args:
            kwargs: 关键字参数。

        Returns:
            工具结果结果。
        """
        local_path = kwargs.get("local_path", "")
        if not local_path:
            return ToolResult(success=False, output="", error="local_path is required for pull")

        full_path = self._validate_local_path(local_path)

        args = ["-C", str(full_path), "pull"]
        result = await self._run_git_command(args)
        if result.success:
            result.metadata["operation"] = "pull"
            result.metadata["local_path"] = str(full_path)
        return result

    async def _do_diff(self, kwargs: dict[str, Any]) -> ToolResult:
        """执行差异。

        Args:
            kwargs: 关键字参数。

        Returns:
            工具结果结果。
        """
        local_path = kwargs.get("local_path", "")
        commit_range = kwargs.get("commit_range", kwargs.get("branch", ""))

        if not local_path:
            return ToolResult(success=False, output="", error="local_path is required for diff")

        full_path = self._validate_local_path(local_path)

        args = ["-C", str(full_path), "diff"]
        if commit_range:
            # 支持 base..head 格式
            if ".." in commit_range:
                args.append(commit_range)
            else:
                # 单个分支名 → diff against that branch
                args.append(f"{commit_range}..HEAD")

        result = await self._run_git_command(args)
        if result.success:
            result.metadata["operation"] = "diff"
            result.metadata["local_path"] = str(full_path)
            result.metadata["commit_range"] = commit_range or "working_tree"
        return result

    async def _do_log(self, kwargs: dict[str, Any]) -> ToolResult:
        """执行日志。

        Args:
            kwargs: 关键字参数。

        Returns:
            工具结果结果。
        """
        local_path = kwargs.get("local_path", "")
        limit = kwargs.get("limit", 20)

        if not local_path:
            return ToolResult(success=False, output="", error="local_path is required for log")

        full_path = self._validate_local_path(local_path)

        # 确保 limit 是正整数
        try:
            limit_int = int(limit)
            if limit_int <= 0:
                limit_int = 20
        except (ValueError, TypeError):
            limit_int = 20

        args = ["-C", str(full_path), "log", "--oneline", f"-n{limit_int}"]
        result = await self._run_git_command(args)
        if result.success:
            result.metadata["operation"] = "log"
            result.metadata["local_path"] = str(full_path)
            result.metadata["limit"] = limit_int
        return result

    async def _do_show(self, kwargs: dict[str, Any]) -> ToolResult:
        """执行显示。

        Args:
            kwargs: 关键字参数。

        Returns:
            工具结果结果。
        """
        local_path = kwargs.get("local_path", "")
        commit = kwargs.get("commit", "")

        if not local_path:
            return ToolResult(success=False, output="", error="local_path is required for show")
        if not commit:
            return ToolResult(success=False, output="", error="commit is required for show")

        # 防止 commit 参数中注入命令（只允许字母数字和常见 git hash 字符）
        if not all(c.isalnum() or c in "._-/" for c in commit):
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid commit hash: '{commit}'",
            )

        full_path = self._validate_local_path(local_path)

        args = ["-C", str(full_path), "show", commit]
        result = await self._run_git_command(args)
        if result.success:
            result.metadata["operation"] = "show"
            result.metadata["local_path"] = str(full_path)
            result.metadata["commit"] = commit
        return result

    async def _do_status(self, kwargs: dict[str, Any]) -> ToolResult:
        """执行状态。

        Args:
            kwargs: 关键字参数。

        Returns:
            工具结果结果。
        """
        local_path = kwargs.get("local_path", "")
        if not local_path:
            return ToolResult(success=False, output="", error="local_path is required for status")

        full_path = self._validate_local_path(local_path)

        args = ["-C", str(full_path), "status", "--porcelain"]
        result = await self._run_git_command(args)
        if result.success:
            result.metadata["operation"] = "status"
            result.metadata["local_path"] = str(full_path)
        return result
