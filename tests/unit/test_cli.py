"""CLI 单元测试 — 命令行参数解析与子命令路由。

测试要点：命令行参数解析、子命令路由、退出码。
"""

from __future__ import annotations

import pytest

from agentforge.cli.main import CLIClient


class TestParserCreation:
    """参数解析器测试。"""

    def test_parser_has_subcommands(self) -> None:
        cli = CLIClient()
        parser = cli._create_parser()
        # Parse --help should not error

        with pytest.raises(SystemExit):
            parser.parse_args(["--help"])

    def test_parser_accepts_url_and_api_key(self) -> None:
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
        cli = CLIClient()
        exit_code = cli.run([])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "agentforge" in captured.out.lower() or "usage" in captured.out.lower()


class TestSubmitCommand:
    """submit 子命令测试。"""

    def test_submit_parses_workflow_and_input(self) -> None:
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
    """status 子命令测试。"""

    def test_status_parses_task_id(self) -> None:
        cli = CLIClient()
        parser = cli._create_parser()
        parsed = parser.parse_args(["status", "task-abc-123"])
        assert parsed.command == "status"
        assert parsed.task_id == "task-abc-123"


class TestServeCommand:
    """serve 子命令测试。"""

    def test_serve_parses_host_and_port(self) -> None:
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
        cli = CLIClient()
        parser = cli._create_parser()
        parsed = parser.parse_args(["serve"])
        assert parsed.host == "0.0.0.0"
        assert parsed.port == 8000


class TestErrorHandling:
    """错误处理测试。"""

    def test_invalid_json_input_returns_error_code(self, capsys) -> None:
        """submit 命令传入无效 JSON 时返回退出码 1。"""
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
        """无法连接时返回退出码 1。"""
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
    """模块级 app 实例测试。"""

    def test_app_is_cli_client(self) -> None:
        from agentforge.cli.main import app

        assert isinstance(app, CLIClient)

    def test_main_function_exists(self) -> None:
        from agentforge.cli.main import main

        assert callable(main)
