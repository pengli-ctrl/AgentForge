"""API App 单元测试 — FastAPI 端点测试。

测试要点：/health、任务提交、任务列表、Agent 列表等端点。
使用 httpx AsyncClient 进行 ASGI 测试。
"""

from __future__ import annotations

import pytest

from agentforge.api.app import create_app


@pytest.fixture
def app():
    """创建测试用 FastAPI 应用（debug 模式，跳过认证）。"""
    return create_app(debug=True, rate_limit_capacity=1000, rate_limit_rate=100)


@pytest.fixture
async def client(app):
    """执行 client 对应的逻辑，并返回处理结果。

    Args:
        app: Any，调用方传入的 app 参数。

    Returns:
        None，函数执行后的结果。
    """
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestHealthEndpoint:
    """健康检查端点测试。"""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client) -> None:
        """验证 health_returns_200 对应的业务行为、边界条件和回归场景。

        Args:
            client: Any，调用方传入的 client 参数。

        Returns:
            None，函数执行后的结果。
        """
        resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_returns_status(self, client) -> None:
        """验证 health_returns_status 对应的业务行为、边界条件和回归场景。

        Args:
            client: Any，调用方传入的 client 参数。

        Returns:
            None，函数执行后的结果。
        """
        resp = await client.get("/health")
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["version"] == "3.0.0"


class TestTaskCreation:
    """任务创建端点测试。"""

    @pytest.mark.asyncio
    async def test_create_task_returns_201(self, client) -> None:
        """验证 create_task_returns_201 对应的业务行为、边界条件和回归场景。

        Args:
            client: Any，调用方传入的 client 参数。

        Returns:
            None，函数执行后的结果。
        """
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "workflow_name": "code-review-pipeline",
                "input_data": {"code_content": "print('hello')"},
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_task_missing_workflow(self, client) -> None:
        """验证 create_task_missing_workflow 对应的业务行为、边界条件和回归场景。

        Args:
            client: Any，调用方传入的 client 参数。

        Returns:
            None，函数执行后的结果。
        """
        resp = await client.post(
            "/api/v1/tasks",
            json={"input_data": {"code": "x"}},
        )
        assert resp.status_code in (400, 422)


class TestTaskListing:
    """任务列表端点测试。"""

    @pytest.mark.asyncio
    async def test_list_tasks_returns_200(self, client) -> None:
        """验证 list_tasks_returns_200 对应的业务行为、边界条件和回归场景。

        Args:
            client: Any，调用方传入的 client 参数。

        Returns:
            None，函数执行后的结果。
        """
        resp = await client.get("/api/v1/tasks")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_tasks_after_creation(self, client) -> None:
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        """验证 list_tasks_after_creation 对应的业务行为、边界条件和回归场景。

        Args:
            client: Any，调用方传入的 client 参数。

        Returns:
            None，函数执行后的结果。
        """
        await client.post(
            "/api/v1/tasks",
            json={
                "workflow_name": "code-review-pipeline",
                "input_data": {"code_content": "x = 1"},
            },
        )
        resp = await client.get("/api/v1/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict))


class TestTaskDetail:
    """任务详情端点测试。"""

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(self, client) -> None:
        """验证 get_nonexistent_task 对应的业务行为、边界条件和回归场景。

        Args:
            client: Any，调用方传入的 client 参数。

        Returns:
            None，函数执行后的结果。
        """
        resp = await client.get("/api/v1/tasks/nonexistent-id")
        assert resp.status_code == 404


class TestAgentEndpoints:
    """Agent 管理端点测试。"""

    @pytest.mark.asyncio
    async def test_list_agents_returns_200(self, client) -> None:
        """验证 list_agents_returns_200 对应的业务行为、边界条件和回归场景。

        Args:
            client: Any，调用方传入的 client 参数。

        Returns:
            None，函数执行后的结果。
        """
        resp = await client.get("/api/v1/agents")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_agents_health_returns_200(self, client) -> None:
        """验证 agents_health_returns_200 对应的业务行为、边界条件和回归场景。

        Args:
            client: Any，调用方传入的 client 参数。

        Returns:
            None，函数执行后的结果。
        """
        resp = await client.get("/api/v1/agents/health")
        assert resp.status_code == 200


class TestMetricsEndpoint:
    """Metrics 端点测试。"""

    @pytest.mark.asyncio
    async def test_metrics_returns_200(self, client) -> None:
        """验证 metrics_returns_200 对应的业务行为、边界条件和回归场景。

        Args:
            client: Any，调用方传入的 client 参数。

        Returns:
            None，函数执行后的结果。
        """
        resp = await client.get("/metrics")
        assert resp.status_code == 200
