"""Git 操作工具 — 代码拉取、diff 获取。

Agent 通过工具注册表调用此工具执行 Git 操作，
获取代码变更内容用于代码审查。

使用 asyncio.create_subprocess_exec 执行 git 命令，
支持 clone、pull、diff、log、show、status 六种安全操作。

安全设计：
- 操作白名单：只允许 clone/pull/diff/log/show/status，拒绝 push/reset 等危险操作
- 仓库 URL 白名单：初始化时传入 allowed_repo_urls，clone 时校验
- 本地路径限制：所有本地路径必须在 workspace 目录内，防止路径遍历攻击
- 参数校验：拼接前校验路径不包含 `..`
- 命令超时：clone/pull 大仓库或网络阻塞时，超时后 kill 子进程避免永久挂起
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from agentforge.core.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class GitTool(BaseTool):
    """Git 操作工具 — 提供代码拉取和 diff 获取功能。

    功能：
    - 克隆仓库到本地 (clone)
    - 拉取最新代码 (pull)
    - 获取 PR diff (diff)
    - 获取提交历史 (log)
    - 查看特定提交 (show)
    - 查看工作区状态 (status)

    安全设计：
    - 不执行 push、force push、reset 等危险操作
    - 仓库 URL 白名单校验
    - 本地路径限制在指定工作目录内
    - 路径遍历攻击防护
    - subprocess 有超时与超时后 kill，避免网络阻塞造成协程永久挂起

    Args:
        workspace: 本地工作目录（克隆的仓库存放在此目录下）。
        allowed_repo_urls: 允许克隆的仓库 URL 白名单。为空则允许所有（开发模式）。
        command_timeout: 单条 git 命令的超时秒数，超时后 kill 子进程。
    """

    # 允许的 Git 操作（白名单）
    ALLOWED_OPS: set[str] = {"clone", "pull", "diff", "log", "show", "status"}

    def __init__(
        self,
        workspace: str = "/tmp/agentforge-workspace",
        allowed_repo_urls: set[str] | None = None,
        command_timeout: float = 60.0,
    ) -> None:
        self.workspace = workspace
        self.allowed_repo_urls = allowed_repo_urls or set()
        self._command_timeout = command_timeout

    @property
    def name(self) -> str:
        """工具唯一标识。"""
        return "git"

    def schema(self) -> dict:
        """返回 JSON Schema。"""
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

        确保路径在 workspace 目录内，不包含 `..`。

        Args:
            local_path: 用户指定的本地路径（相对或绝对）。

        Returns:
            校验后的绝对路径。

        Raises:
            ValueError: 路径包含 `..` 或超出 workspace 范围。
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
            repo_url: 仓库 URL。

        Raises:
            ValueError: URL 不在白名单中。
        """
        if self.allowed_repo_urls and repo_url not in self.allowed_repo_urls:
            raise ValueError(
                f"Repository URL '{repo_url}' is not in the allowed list. "
                f"Allowed: {self.allowed_repo_urls}"
            )

    async def _run_git_command(self, args: list[str]) -> ToolResult:
        """执行 git 命令并返回结果。

        使用 asyncio.create_subprocess_exec 异步执行 git 命令，
        捕获 stdout 和 stderr。通过 ``asyncio.wait_for`` 对
        ``communicate()`` 施加超时；超时后 kill 子进程并回收，
        避免 clone/pull 大仓库或网络阻塞时协程永久挂起。

        Args:
            args: git 命令参数列表（不含 "git" 前缀）。

        Returns:
            工具执行结果。退出码非 0 时 success=False，超时同样 success=False。
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
        """Terminate a stuck subprocess and reap it so no zombie remains.

        Args:
            process: The subprocess to kill.
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
        """执行 Git 操作。

        根据 operation 参数分派到具体的 git 子命令。
        所有操作都经过安全校验（白名单、路径限制、URL 校验）。

        Args:
            operation: Git 操作类型（clone/pull/diff/log/show/status）。
            repo_url: 仓库 URL（clone 操作时需要）。
            local_path: 本地路径（仓库在 workspace 中的位置）。
            branch: 分支名称（clone 时可指定分支）。
            commit_range: 提交范围（diff 操作时使用，如 main...feature）。
            limit: 日志条数（log 操作时使用，默认 20）。
            commit: 提交哈希（show 操作时使用）。

        Returns:
            Git 操作结果。
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
        """执行 git clone。

        Args:
            kwargs: 包含 repo_url, local_path, branch。

        Returns:
            克隆结果。
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
        """执行 git pull。

        Args:
            kwargs: 包含 local_path。

        Returns:
            拉取结果。
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
        """执行 git diff。

        Args:
            kwargs: 包含 local_path, commit_range（可选，如 main...feature）。

        Returns:
            diff 结果。
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
        """执行 git log。

        Args:
            kwargs: 包含 local_path, limit（默认 20）。

        Returns:
            日志结果。
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
        """执行 git show。

        Args:
            kwargs: 包含 local_path, commit。

        Returns:
            show 结果。
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
        """执行 git status。

        Args:
            kwargs: 包含 local_path。

        Returns:
            status 结果。
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
