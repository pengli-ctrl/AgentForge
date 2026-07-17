"""FastAPI 应用入口 — 注册路由和中间件。

创建 FastAPI 应用实例，注册所有路由和中间件。
支持通过环境变量配置认证、限流等参数。

启动方式：
    uvicorn agentforge.api.app:app --host 0.0.0.0 --port 8000

环境变量：
    AGENTFORGE_API_KEYS: 逗号分隔的 API Key 列表
    AGENTFORGE_DEBUG: 是否启用 DEBUG 模式（true/false）
    AGENTFORGE_RATE_LIMIT_CAPACITY: 限流桶容量
    AGENTFORGE_RATE_LIMIT_RATE: 限流速率（请求/秒）
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agentforge.api.middleware.auth import AuthMiddleware
from agentforge.api.middleware.error_handler import APIError, ErrorHandlerMiddleware
from agentforge.api.middleware.rate_limit import RateLimitMiddleware
from agentforge.api.routes.agents import AgentRoutes
from agentforge.api.routes.metrics import MetricsRoutes
from agentforge.api.routes.tasks import TaskRoutes
from agentforge.storage.task_store import TaskStore
from agentforge.workflow.registry import AgentRegistry

logger = logging.getLogger(__name__)


def create_app(
    task_store: TaskStore | None = None,
    agent_registry: AgentRegistry | None = None,
    workflow_engine: Any = None,
    api_keys: set[str] | None = None,
    debug: bool = False,
    rate_limit_capacity: float = 100.0,
    rate_limit_rate: float = 10.0,
) -> Any:
    """创建 FastAPI 应用实例。

    Args:
        task_store: 任务存储实例（不传则创建内存存储）。
        agent_registry: Agent 注册表（不传则创建空注册表）。
        workflow_engine: 工作流引擎实例（可选）。
        api_keys: 合法的 API Key 集合。
        debug: 是否启用 DEBUG 模式。
        rate_limit_capacity: 限流桶容量。
        rate_limit_rate: 限流速率。

    Returns:
        FastAPI 应用实例。
    """
    # 初始化中间件
    env_api_keys = os.environ.get("AGENTFORGE_API_KEYS", "")
    if env_api_keys and api_keys is None:
        api_keys = set(env_api_keys.split(","))
    env_debug = os.environ.get("AGENTFORGE_DEBUG", "").lower() == "true"
    debug = debug or env_debug

    # 初始化依赖
    task_store = task_store or TaskStore()
    agent_registry = agent_registry or AgentRegistry()

    # 初始化中间件
    auth_middleware = AuthMiddleware(
        api_keys=api_keys or set(),
        allow_no_auth=debug,
    )
    rate_limit_middleware = RateLimitMiddleware(
        capacity=rate_limit_capacity,
        rate=rate_limit_rate,
    )
    error_handler = ErrorHandlerMiddleware(debug=debug)

    # 初始化路由处理器
    task_routes = TaskRoutes(
        task_store=task_store,
        workflow_engine=workflow_engine,
    )
    agent_routes = AgentRoutes(registry=agent_registry)
    metrics_routes = MetricsRoutes()

    # 创建 FastAPI 应用
    app = FastAPI(
        title="AgentForge API",
        description="事件驱动的多 Agent 编排框架 REST API",
        version="3.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # --- 中间件 ---

    @app.middleware("http")
    async def auth_and_rate_limit(request: Request, call_next):
        """认证 + 限流中间件。"""
        # 认证
        headers = dict(request.headers)
        if not auth_middleware.authenticate(headers, request.url.path):
            error = APIError(
                code="UNAUTHORIZED",
                message="Invalid or missing API key",
                status_code=401,
            )
            return JSONResponse(
                status_code=401,
                content=error.to_dict(include_detail=debug),
            )

        # 限流
        client_id = headers.get("x-api-key", request.client.host if request.client else "unknown")
        if not rate_limit_middleware.check(client_id):
            error = APIError(
                code="RATE_LIMITED",
                message="Rate limit exceeded. Please retry later.",
                status_code=429,
            )
            return JSONResponse(
                status_code=429,
                content=error.to_dict(include_detail=debug),
                headers={"Retry-After": "60"},
            )

        return await call_next(request)

    # --- 健康检查 ---

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """健康检查端点。"""
        return {"status": "healthy", "version": "3.0.0"}

    # --- 任务管理路由 ---

    @app.post("/api/v1/tasks")
    async def create_task(request: Request) -> JSONResponse:
        """提交新任务。"""
        try:
            body = await request.json()
            result = await task_routes.create_task(body)
            return JSONResponse(status_code=201, content=result)
        except APIError as e:
            return JSONResponse(
                status_code=e.status_code,
                content=error_handler.handle_api_error(e).to_dict(debug),
            )
        except Exception as e:
            api_error = error_handler.handle_exception(e)
            return JSONResponse(
                status_code=api_error.status_code,
                content=api_error.to_dict(debug),
            )

    @app.get("/api/v1/tasks")
    async def list_tasks(
        status: str | None = None, limit: int = 50, offset: int = 0
    ) -> JSONResponse:
        """查询任务列表。"""
        try:
            result = await task_routes.list_tasks(status, limit, offset)
            return JSONResponse(content=result)
        except APIError as e:
            return JSONResponse(
                status_code=e.status_code,
                content=error_handler.handle_api_error(e).to_dict(debug),
            )
        except Exception as e:
            api_error = error_handler.handle_exception(e)
            return JSONResponse(
                status_code=api_error.status_code,
                content=api_error.to_dict(debug),
            )

    @app.get("/api/v1/tasks/{task_id}")
    async def get_task(task_id: str) -> JSONResponse:
        """查询任务详情。"""
        try:
            result = await task_routes.get_task(task_id)
            return JSONResponse(content=result)
        except APIError as e:
            return JSONResponse(
                status_code=e.status_code,
                content=error_handler.handle_api_error(e).to_dict(debug),
            )
        except Exception as e:
            api_error = error_handler.handle_exception(e)
            return JSONResponse(
                status_code=api_error.status_code,
                content=api_error.to_dict(debug),
            )

    @app.get("/api/v1/tasks/{task_id}/result")
    async def get_task_result(task_id: str) -> JSONResponse:
        """获取任务结果。"""
        try:
            result = await task_routes.get_task_result(task_id)
            return JSONResponse(content=result)
        except APIError as e:
            return JSONResponse(
                status_code=e.status_code,
                content=error_handler.handle_api_error(e).to_dict(debug),
            )
        except Exception as e:
            api_error = error_handler.handle_exception(e)
            return JSONResponse(
                status_code=api_error.status_code,
                content=api_error.to_dict(debug),
            )

    @app.post("/api/v1/tasks/{task_id}/cancel")
    async def cancel_task(task_id: str) -> JSONResponse:
        """取消任务。"""
        try:
            result = await task_routes.cancel_task(task_id)
            return JSONResponse(content=result)
        except APIError as e:
            return JSONResponse(
                status_code=e.status_code,
                content=error_handler.handle_api_error(e).to_dict(debug),
            )
        except Exception as e:
            api_error = error_handler.handle_exception(e)
            return JSONResponse(
                status_code=api_error.status_code,
                content=api_error.to_dict(debug),
            )

    # --- Agent 管理路由 ---

    @app.get("/api/v1/agents")
    async def list_agents() -> JSONResponse:
        """查询 Agent 列表。"""
        result = await agent_routes.list_agents()
        return JSONResponse(content=result)

    @app.get("/api/v1/agents/health")
    async def agents_health() -> JSONResponse:
        """Agent 健康检查。"""
        result = await agent_routes.health_check()
        return JSONResponse(content=result)

    @app.get("/api/v1/agents/{name}")
    async def get_agent(name: str) -> JSONResponse:
        """查询单个 Agent 详情。"""
        try:
            result = await agent_routes.get_agent(name)
            return JSONResponse(content=result)
        except APIError as e:
            return JSONResponse(
                status_code=e.status_code,
                content=error_handler.handle_api_error(e).to_dict(debug),
            )

    # --- 指标路由 ---

    @app.get("/metrics")
    async def get_metrics():
        """Prometheus 指标端点。"""
        from fastapi.responses import PlainTextResponse

        result = await metrics_routes.get_metrics()
        return PlainTextResponse(content=result, media_type="text/plain")

    # 存储依赖到 app.state，便于测试访问
    app.state.task_store = task_store
    app.state.agent_registry = agent_registry
    app.state.auth_middleware = auth_middleware
    app.state.rate_limit_middleware = rate_limit_middleware

    logger.info("AgentForge API app created (debug=%s)", debug)
    return app
