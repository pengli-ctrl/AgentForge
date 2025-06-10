"""GitTool 单元测试 — 真实 subprocess 调用 + 安全校验。

测试要点：
- 各操作（clone/pull/diff/log/show/status）的命令构建
- 安全校验：操作白名单、路径遍历防护、URL 白名单
- 错误处理：git 退出码非 0、git 未安装
- subprocess mock 验证
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agentforge.tools.git_tool import GitTool

# ──────────────────────────────────────────────────────────────────────────
# 辅助函数 — mock asyncio.create_subprocess_exec
# ──────────────────────────────────────────────────────────────────────────


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
    process = AsyncMock()
    process.communicate = AsyncMock(return_value=(stdout, stderr))
    process.returncode = returncode
    return process


# ──────────────────────────────────────────────────────────────────────────
# 基础测试
# ──────────────────────────────────────────────────────────────────────────


class TestGitToolBasic:
    """GitTool 基础属性测试。"""

    def test_name(self) -> None:
        tool = GitTool()
        assert tool.name == "git"

    def test_schema(self) -> None:
        tool = GitTool()
        schema = tool.schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "git"
        assert "operation" in schema["function"]["parameters"]["properties"]
        assert "clone" in schema["function"]["parameters"]["properties"]["operation"]["enum"]
        assert "pull" in schema["function"]["parameters"]["properties"]["operation"]["enum"]
        assert "diff" in schema["function"]["parameters"]["properties"]["operation"]["enum"]
        assert "log" in schema["function"]["parameters"]["properties"]["operation"]["enum"]
        assert "show" in schema["function"]["parameters"]["properties"]["operation"]["enum"]
        assert "status" in schema["function"]["parameters"]["properties"]["operation"]["enum"]
        # 确认危险操作不在白名单
        assert "push" not in schema["function"]["parameters"]["properties"]["operation"]["enum"]
        assert "reset" not in schema["function"]["parameters"]["properties"]["operation"]["enum"]

    def test_init_defaults(self) -> None:
        tool = GitTool()
        assert tool.workspace == "/tmp/agentforge-workspace"
        assert tool.allowed_repo_urls == set()

    def test_init_with_allowed_urls(self) -> None:
        tool = GitTool(
            workspace="/custom/workspace",
            allowed_repo_urls={"https://github.com/org/repo.git"},
        )
        assert tool.workspace == "/custom/workspace"
        assert "https://github.com/org/repo.git" in tool.allowed_repo_urls


# ──────────────────────────────────────────────────────────────────────────
# 操作白名单测试
# ──────────────────────────────────────────────────────────────────────────


class TestGitToolOperationWhitelist:
    """GitTool 操作白名单测试。"""

    @pytest.mark.asyncio
    async def test_disallowed_operation(self) -> None:
        """非白名单操作被拒绝。"""
        tool = GitTool()
        result = await tool.execute(operation="push", repo_url="x", local_path="y")
        assert result.success is False
        assert "not allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_reset_rejected(self) -> None:
        """reset 操作被拒绝。"""
        tool = GitTool()
        result = await tool.execute(operation="reset", local_path="repo")
        assert result.success is False
        assert "not allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_force_push_rejected(self) -> None:
        """force-push 操作被拒绝。"""
        tool = GitTool()
        result = await tool.execute(operation="force-push", local_path="repo")
        assert result.success is False


# ──────────────────────────────────────────────────────────────────────────
# 安全校验测试
# ──────────────────────────────────────────────────────────────────────────


class TestGitToolSecurity:
    """GitTool 安全校验测试。"""

    @pytest.mark.asyncio
    async def test_path_traversal_rejected(self) -> None:
        """路径包含 `..` 被拒绝。"""
        tool = GitTool(workspace="/tmp/ws")
        result = await tool.execute(operation="pull", local_path="../../../etc/passwd")
        assert result.success is False
        assert "traversal" in result.error.lower()

    @pytest.mark.asyncio
    async def test_path_outside_workspace_rejected(self) -> None:
        """绝对路径超出 workspace 被拒绝。"""
        tool = GitTool(workspace="/tmp/ws")
        result = await tool.execute(operation="pull", local_path="/etc/passwd")
        assert result.success is False
        assert "outside" in result.error.lower()

    @pytest.mark.asyncio
    async def test_repo_url_not_in_whitelist(self) -> None:
        """仓库 URL 不在白名单被拒绝。"""
        tool = GitTool(
            workspace="/tmp/ws",
            allowed_repo_urls={"https://github.com/allowed/repo.git"},
        )
        result = await tool.execute(
            operation="clone",
            repo_url="https://github.com/evil/repo.git",
            local_path="repo",
        )
        assert result.success is False
        assert "not in the allowed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_repo_url_in_whitelist_passes(self) -> None:
        """白名单内的 URL 通过校验（但 git 命令可能因不存在而失败）。"""
        tool = GitTool(
            workspace="/tmp/ws",
            allowed_repo_urls={"https://github.com/allowed/repo.git"},
        )
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _make_mock_process(
                stdout=b"Cloning into...",
                returncode=0,
            )
            result = await tool.execute(
                operation="clone",
                repo_url="https://github.com/allowed/repo.git",
                local_path="repo",
            )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_empty_whitelist_allows_all(self) -> None:
        """空白名单允许所有 URL（开发模式）。"""
        tool = GitTool(workspace="/tmp/ws", allowed_repo_urls=set())
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _make_mock_process(returncode=0)
            result = await tool.execute(
                operation="clone",
                repo_url="https://anywhere.com/repo.git",
                local_path="repo",
            )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_invalid_commit_hash_rejected(self) -> None:
        """show 操作的 commit 参数包含非法字符被拒绝。"""
        tool = GitTool(workspace="/tmp/ws")
        result = await tool.execute(
            operation="show",
            local_path="repo",
            commit="abc; rm -rf /",
        )
        assert result.success is False
        assert "invalid" in result.error.lower()


# ──────────────────────────────────────────────────────────────────────────
# Clone 操作测试
# ──────────────────────────────────────────────────────────────────────────


class TestGitToolClone:
    """GitTool clone 操作测试。"""

    @pytest.mark.asyncio
    async def test_clone_success(self) -> None:
        """成功 clone 仓库。"""
        tool = GitTool(workspace="/tmp/ws")
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _make_mock_process(
                stdout=b"Cloning into '/tmp/ws/repo'...",
                returncode=0,
            )
            result = await tool.execute(
                operation="clone",
                repo_url="https://github.com/test/repo.git",
                local_path="repo",
            )

        assert result.success is True
        assert "Cloning" in result.output
        # 验证 git 命令参数
        args = mock_exec.call_args[0]
        assert args[0] == "git"
        assert "clone" in args
        assert "https://github.com/test/repo.git" in args

    @pytest.mark.asyncio
    async def test_clone_with_branch(self) -> None:
        """clone 指定分支。"""
        tool = GitTool(workspace="/tmp/ws")
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _make_mock_process(returncode=0)
            result = await tool.execute(
                operation="clone",
                repo_url="https://github.com/test/repo.git",
                local_path="repo",
                branch="develop",
            )

        assert result.success is True
        args = mock_exec.call_args[0]
        assert "-b" in args
        assert "develop" in args

    @pytest.mark.asyncio
    async def test_clone_missing_repo_url(self) -> None:
        """clone 缺少 repo_url 返回错误。"""
        tool = GitTool(workspace="/tmp/ws")
        result = await tool.execute(operation="clone", local_path="repo")
        assert result.success is False
        assert "repo_url" in result.error

    @pytest.mark.asyncio
    async def test_clone_missing_local_path(self) -> None:
        """clone 缺少 local_path 返回错误。"""
        tool = GitTool(workspace="/tmp/ws")
        result = await tool.execute(operation="clone", repo_url="https://x.com/r.git")
        assert result.success is False
        assert "local_path" in result.error

    @pytest.mark.asyncio
    async def test_clone_failure(self) -> None:
        """clone 失败（git 退出码非 0）。"""
        tool = GitTool(workspace="/tmp/ws")
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _make_mock_process(
                stderr=b"fatal: repository not found",
                returncode=128,
            )
            result = await tool.execute(
                operation="clone",
                repo_url="https://github.com/test/nonexistent.git",
                local_path="repo",
            )

        assert result.success is False
        assert "repository not found" in result.error


# ──────────────────────────────────────────────────────────────────────────
# Pull 操作测试
# ──────────────────────────────────────────────────────────────────────────


class TestGitToolPull:
    """GitTool pull 操作测试。"""

    @pytest.mark.asyncio
    async def test_pull_success(self) -> None:
        """成功 pull。"""
        tool = GitTool(workspace="/tmp/ws")
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _make_mock_process(
                stdout=b"Already up to date.",
                returncode=0,
            )
            result = await tool.execute(operation="pull", local_path="repo")

        assert result.success is True
        assert "Already up to date" in result.output
        args = mock_exec.call_args[0]
        assert args[0] == "git"
        assert "-C" in args
        assert "pull" in args

    @pytest.mark.asyncio
    async def test_pull_missing_local_path(self) -> None:
        """pull 缺少 local_path 返回错误。"""
        tool = GitTool(workspace="/tmp/ws")
        result = await tool.execute(operation="pull")
        assert result.success is False
        assert "local_path" in result.error


# ──────────────────────────────────────────────────────────────────────────
# Diff 操作测试
# ──────────────────────────────────────────────────────────────────────────


class TestGitToolDiff:
    """GitTool diff 操作测试。"""

    @pytest.mark.asyncio
    async def test_diff_without_range(self) -> None:
        """无 commit_range 的 diff（工作区变更）。"""
        tool = GitTool(workspace="/tmp/ws")
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _make_mock_process(
                stdout=b"diff --git a/file b/file",
                returncode=0,
            )
            result = await tool.execute(operation="diff", local_path="repo")

        assert result.success is True
        args = mock_exec.call_args[0]
        assert "diff" in args

    @pytest.mark.asyncio
    async def test_diff_with_commit_range(self) -> None:
        """有 commit_range 的 diff。"""
        tool = GitTool(workspace="/tmp/ws")
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _make_mock_process(
                stdout=b"diff content",
                returncode=0,
            )
            result = await tool.execute(
                operation="diff",
                local_path="repo",
                commit_range="main...feature",
            )

        assert result.success is True
        args = mock_exec.call_args[0]
        assert "main...feature" in args

    @pytest.mark.asyncio
    async def test_diff_missing_local_path(self) -> None:
        """diff 缺少 local_path 返回错误。"""
        tool = GitTool(workspace="/tmp/ws")
        result = await tool.execute(operation="diff")
        assert result.success is False
        assert "local_path" in result.error


# ──────────────────────────────────────────────────────────────────────────
# Log 操作测试
# ──────────────────────────────────────────────────────────────────────────


class TestGitToolLog:
    """GitTool log 操作测试。"""

    @pytest.mark.asyncio
    async def test_log_default_limit(self) -> None:
        """log 默认限制 20 条。"""
        tool = GitTool(workspace="/tmp/ws")
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _make_mock_process(
                stdout=b"abc1234 commit message\n",
                returncode=0,
            )
            result = await tool.execute(operation="log", local_path="repo")

        assert result.success is True
        args = mock_exec.call_args[0]
        assert "log" in args
        assert "--oneline" in args
        assert "-n20" in args

    @pytest.mark.asyncio
    async def test_log_custom_limit(self) -> None:
        """log 自定义条数。"""
        tool = GitTool(workspace="/tmp/ws")
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _make_mock_process(
                stdout=b"abc1234 message\n",
                returncode=0,
            )
            result = await tool.execute(operation="log", local_path="repo", limit=5)

        assert result.success is True
        args = mock_exec.call_args[0]
        assert "-n5" in args

    @pytest.mark.asyncio
    async def test_log_invalid_limit_fallback(self) -> None:
        """limit 非法时使用默认值 20。"""
        tool = GitTool(workspace="/tmp/ws")
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _make_mock_process(returncode=0)
            await tool.execute(operation="log", local_path="repo", limit="not-a-number")

        args = mock_exec.call_args[0]
        assert "-n20" in args


# ──────────────────────────────────────────────────────────────────────────
# Show 操作测试
# ──────────────────────────────────────────────────────────────────────────


class TestGitToolShow:
    """GitTool show 操作测试。"""

    @pytest.mark.asyncio
    async def test_show_success(self) -> None:
        """成功 show commit。"""
        tool = GitTool(workspace="/tmp/ws")
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _make_mock_process(
                stdout=b"commit abc1234\nAuthor: Test\n",
                returncode=0,
            )
            result = await tool.execute(
                operation="show",
                local_path="repo",
                commit="abc1234",
            )

        assert result.success is True
        assert "abc1234" in result.output
        args = mock_exec.call_args[0]
        assert "show" in args
        assert "abc1234" in args

    @pytest.mark.asyncio
    async def test_show_missing_commit(self) -> None:
        """show 缺少 commit 返回错误。"""
        tool = GitTool(workspace="/tmp/ws")
        result = await tool.execute(operation="show", local_path="repo")
        assert result.success is False
        assert "commit" in result.error


# ──────────────────────────────────────────────────────────────────────────
# Status 操作测试
# ──────────────────────────────────────────────────────────────────────────


class TestGitToolStatus:
    """GitTool status 操作测试。"""

    @pytest.mark.asyncio
    async def test_status_success(self) -> None:
        """成功获取 status。"""
        tool = GitTool(workspace="/tmp/ws")
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _make_mock_process(
                stdout=b" M modified_file.py\n",
                returncode=0,
            )
            result = await tool.execute(operation="status", local_path="repo")

        assert result.success is True
        assert "modified_file.py" in result.output
        args = mock_exec.call_args[0]
        assert "status" in args
        assert "--porcelain" in args

    @pytest.mark.asyncio
    async def test_status_missing_local_path(self) -> None:
        """status 缺少 local_path 返回错误。"""
        tool = GitTool(workspace="/tmp/ws")
        result = await tool.execute(operation="status")
        assert result.success is False
        assert "local_path" in result.error


# ──────────────────────────────────────────────────────────────────────────
# 错误处理测试
# ──────────────────────────────────────────────────────────────────────────


class TestGitToolErrorHandling:
    """GitTool 错误处理测试。"""

    @pytest.mark.asyncio
    async def test_git_not_installed(self) -> None:
        """git 未安装时返回友好错误。"""
        tool = GitTool(workspace="/tmp/ws")
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = FileNotFoundError("git not found")
            result = await tool.execute(operation="status", local_path="repo")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_git_nonzero_exit(self) -> None:
        """git 退出码非 0 返回 stderr。"""
        tool = GitTool(workspace="/tmp/ws")
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _make_mock_process(
                stderr=b"fatal: not a git repository",
                returncode=128,
            )
            result = await tool.execute(operation="status", local_path="repo")

        assert result.success is False
        assert "not a git repository" in result.error
        assert result.metadata.get("returncode") == 128

    @pytest.mark.asyncio
    async def test_subprocess_exception(self) -> None:
        """子进程异常时返回错误。"""
        tool = GitTool(workspace="/tmp/ws")
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.side_effect = PermissionError("permission denied")
            result = await tool.execute(operation="status", local_path="repo")

        assert result.success is False
        assert "Failed to execute" in result.error
