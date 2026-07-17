"""CLI 入口 — 基于 typer 的命令行工具。

支持以下命令：
    agentforge submit <workflow> <input_file>  — 提交任务
    agentforge status <task_id>                 — 查看任务状态
    agentforge result <task_id>                 — 获取任务结果
    agentforge agents                           — 查看 Agent 列表
    agentforge metrics                          — 查看 Metrics
    agentforge workflows                        — 查看可用工作流
    agentforge serve                            — 启动 API 服务

使用方式：
    agentforge submit code-review-pipeline --input '{"code_content": "..."}'
    agentforge status task-abc-123
    agentforge agents
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


class CLIClient:
    """CLI 命令行工具 — 提供交互式命令行接口。

    不依赖外部 CLI 框架（typer/click），使用标准库 argparse 实现，
    减少依赖。支持通过 SDK 客户端与 AgentForge API 交互。

    Args:
        base_url: AgentForge API 基础 URL。
        api_key: API Key。
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str = "",
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key

    def run(self, args: list[str] | None = None) -> int:
        """运行 CLI 命令。

        Args:
            args: 命令行参数列表（None 时使用 sys.argv）。

        Returns:
            退出码（0=成功，1=失败）。
        """
        parser = self._create_parser()
        parsed = parser.parse_args(args)

        if not parsed.command:
            parser.print_help()
            return 0

        try:
            asyncio.run(self._dispatch(parsed))
            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            logger.error("CLI command failed: %s", e, exc_info=True)
            return 1

    def _create_parser(self) -> Any:
        """创建命令行参数解析器。"""
        import argparse

        parser = argparse.ArgumentParser(
            prog="agentforge",
            description="AgentForge — 事件驱动的多 Agent 编排框架 CLI",
        )

        parser.add_argument(
            "--url",
            default="http://localhost:8000",
            help="AgentForge API URL (default: http://localhost:8000)",
        )
        parser.add_argument(
            "--api-key",
            default="",
            help="API Key for authentication",
        )

        subparsers = parser.add_subparsers(dest="command")

        # submit
        submit_parser = subparsers.add_parser("submit", help="Submit a new task")
        submit_parser.add_argument("workflow", help="Workflow name")
        submit_parser.add_argument(
            "--input",
            default="{}",
            help="Input data as JSON string",
        )
        submit_parser.add_argument(
            "--priority",
            default="task_primary",
            help="Task priority (default: task_primary)",
        )

        # status
        status_parser = subparsers.add_parser("status", help="Get task status")
        status_parser.add_argument("task_id", help="Task ID")

        # result
        result_parser = subparsers.add_parser("result", help="Get task result")
        result_parser.add_argument("task_id", help="Task ID")

        # cancel
        cancel_parser = subparsers.add_parser("cancel", help="Cancel a task")
        cancel_parser.add_argument("task_id", help="Task ID")

        # agents
        subparsers.add_parser("agents", help="List registered agents")

        # metrics
        subparsers.add_parser("metrics", help="Show Prometheus metrics")

        # workflows
        subparsers.add_parser("workflows", help="List available workflows")

        # serve
        serve_parser = subparsers.add_parser("serve", help="Start API server")
        serve_parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
        serve_parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")

        return parser

    async def _dispatch(self, parsed: Any) -> None:
        """分发命令到对应的处理方法。

        Args:
            parsed: 解析后的命令行参数。
        """
        from agentforge.sdk.client import AgentForgeClient

        client = AgentForgeClient(
            base_url=parsed.url,
            api_key=parsed.api_key,
        )

        try:
            if parsed.command == "submit":
                input_data = json.loads(parsed.input)
                result = await client.submit_task(
                    workflow_name=parsed.workflow,
                    input_data=input_data,
                    priority=parsed.priority,
                )
                print(json.dumps(result, indent=2, ensure_ascii=False))

            elif parsed.command == "status":
                result = await client.get_task_status(parsed.task_id)
                print(json.dumps(result, indent=2, ensure_ascii=False))

            elif parsed.command == "result":
                result = await client.get_task_result(parsed.task_id)
                print(json.dumps(result, indent=2, ensure_ascii=False))

            elif parsed.command == "cancel":
                result = await client.cancel_task(parsed.task_id)
                print(json.dumps(result, indent=2, ensure_ascii=False))

            elif parsed.command == "agents":
                result = await client.list_agents()
                print(json.dumps(result, indent=2, ensure_ascii=False))

            elif parsed.command == "metrics":
                result = await client.get_metrics()
                print(result)

            elif parsed.command == "workflows":
                import os

                workflow_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    "configs",
                    "workflows",
                )
                if os.path.exists(workflow_dir):
                    workflows = [f[:-5] for f in os.listdir(workflow_dir) if f.endswith(".yaml")]
                    print(json.dumps({"workflows": sorted(workflows)}, indent=2))
                else:
                    print(json.dumps({"workflows": []}, indent=2))

            elif parsed.command == "serve":
                await self._serve(parsed.host, parsed.port)

        finally:
            await client.close()

    async def _serve(self, host: str, port: int) -> None:
        """启动 API 服务。

        Args:
            host: 监听地址。
            port: 监听端口。
        """
        try:
            import uvicorn

            from agentforge.api.app import create_app

            app = create_app()
            config = uvicorn.Config(app, host=host, port=port, log_level="info")
            server = uvicorn.Server(config)
            await server.serve()
        except ImportError:
            print("uvicorn is required to serve. Install with: pip install uvicorn")


# 模块级 app 实例（兼容 typer 风格的导入）
app = CLIClient()


def main() -> int:
    """CLI 主入口函数。

    Returns:
        退出码。
    """
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
