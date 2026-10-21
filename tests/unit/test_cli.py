"""CLI 单元测试 — 命令行参数解析与子命令路由。

测试要点：命令行参数解析、子命令路由、退出码。
"""

from __future__ import annotations

import pytest

from agentforge.cli.main import CLIClient


class TestParserCreation:
    """参数解析器测试。"""

    def test_parser_has_subcommands(self) -> None:
        """验证解析器具有对应的测试场景。"""
        cli = CLIClient()
        parser = cli._create_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["--help"])

    def test_parser_accepts_url_and_api_key(self) -> None:
        """验证解析器URL及API键对应的测试场景。"""
        cli = CLIClient()
        parser = cli._create_parser()
        parsed = parser.parse_args(
            [
                "--url",
                "http://custom:8080",
                "--api-key",
                "mykey",
                "status",
                "task-123",
            ]
        )
        assert parsed.url == "http://custom:8080"
        assert parsed.api_key == "mykey"
        assert parsed.command == "status"
        assert parsed.task_id == "task-123"


class TestNoCommand:
    """无子命令测试。"""

    def test_no_command_prints_help_returns_zero(self, capsys) -> None:
        """验证无返回零对应的测试场景。

        Args:
            capsys: 输入参数。
        """
        cli = CLIClient()
        exit_code = cli.run([])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "agentforge" in captured.out.lower() or "usage" in captured.out.lower()


class TestSubmitCommand:
    """验证测试提交行为的测试集合。"""

    def test_submit_parses_workflow_and_input(self) -> None:
        """验证提交解析工作流及输入对应的测试场景。"""
        cli = CLIClient()
        parser = cli._create_parser()
        parsed = parser.parse_args(
            [
                "submit",
                "code-review-pipeline",
                "--input",
                '{"code": "x"}',
                "--priority",
                "batch",
            ]
        )
        assert parsed.command == "submit"
        assert parsed.workflow == "code-review-pipeline"
        assert parsed.input == '{"code": "x"}'
        assert parsed.priority == "batch"


class TestStatusCommand:
    """验证测试状态行为的测试集合。"""

    def test_status_parses_task_id(self) -> None:
        """验证状态解析任务ID对应的测试场景。"""
        cli = CLIClient()
        parser = cli._create_parser()
        parsed = parser.parse_args(["status", "task-abc-123"])
        assert parsed.command == "status"
        assert parsed.task_id == "task-abc-123"


class TestServeCommand:
    """验证测试提供行为的测试集合。"""

    def test_serve_parses_host_and_port(self) -> None:
        """验证提供解析及对应的测试场景。"""
        cli = CLIClient()
        parser = cli._create_parser()
        parsed = parser.parse_args(
            [
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                "9000",
            ]
        )
        assert parsed.command == "serve"
        assert parsed.host == "127.0.0.1"
        assert parsed.port == 9000

    def test_serve_defaults(self) -> None:
        """验证提供默认项对应的测试场景。"""
        cli = CLIClient()
        parser = cli._create_parser()
        parsed = parser.parse_args(["serve"])
        assert parsed.host == "0.0.0.0"
        assert parsed.port == 8000


class TestErrorHandling:
    """错误处理测试。"""

    def test_invalid_json_input_returns_error_code(self, capsys) -> None:
        """验证无效JSON输入返回错误代码对应的测试场景。

        Args:
            capsys: 输入参数。
        """
        cli = CLIClient()
        exit_code = cli.run(
            [
                "--url",
                "http://localhost:8000",
                "submit",
                "test-workflow",
                "--input",
                "not valid json",
            ]
        )
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_connection_error_returns_error_code(self, capsys) -> None:
        """无法连接时返回退出码 1。

        Args:
            capsys: 输入参数。
        """
        cli = CLIClient()
        exit_code = cli.run(
            [
                "--url",
                "http://nonexistent-host:9999",
                "status",
                "task-1",
            ]
        )
        assert exit_code == 1


class TestModuleLevelApp:
    """验证测试模块级别应用行为的测试集合。"""

    def test_app_is_cli_client(self) -> None:
        """验证应用是否客户端对应的测试场景。"""
        from agentforge.cli.main import app

        assert isinstance(app, CLIClient)

    def test_main_function_exists(self) -> None:
        """验证函数存在对应的测试场景。"""
        from agentforge.cli.main import main

        assert callable(main)
