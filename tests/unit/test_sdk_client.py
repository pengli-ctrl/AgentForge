"""SDK Client 单元测试 — HTTP 客户端、请求构建、响应解析。

测试要点：HTTP客户端、请求构建、响应解析。
使用 Mock httpx client 模拟 HTTP 请求。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentforge.sdk.client import AgentForgeClient


class TestClientInit:
    """客户端初始化测试。"""

    def test_defaults(self) -> None:
        client = AgentForgeClient()
        assert client.base_url == "http://localhost:8000"
        assert client.api_key == ""
        assert client.timeout == 30.0

    def test_custom_values(self) -> None:
        client = AgentForgeClient(
            base_url="http://my-server:9000/",
            api_key="secret",
            timeout=15.0,
        )
        assert client.base_url == "http://my-server:9000"  # trailing slash stripped
        assert client.api_key == "secret"
        assert client.timeout == 15.0

    def test_client_starts_lazy(self) -> None:
        client = AgentForgeClient()
        assert client._client is None


class TestSubmitTask:
    """提交任务测试。"""

    @pytest.mark.asyncio
    async def test_submit_task_builds_correct_request(self) -> None:
        client = AgentForgeClient(api_key="test-key")

        mock_response = MagicMock()
        mock_response.json.return_value = {"task_id": "t-1", "status": "pending"}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.submit_task(
                workflow_name="code-review-pipeline",
                input_data={"code": "x"},
                priority="task_primary",
            )

        assert result["task_id"] == "t-1"
        mock_http.post.assert_awaited_once()
        call_kwargs = mock_http.post.call_args
        assert call_kwargs[0][0] == "/api/v1/tasks"
        body = call_kwargs[1]["json"]
        assert body["workflow_name"] == "code-review-pipeline"
        assert body["input_data"] == {"code": "x"}
        assert body["priority"] == "task_primary"


class TestGetTaskStatus:
    """查询任务状态测试。"""

    @pytest.mark.asyncio
    async def test_get_status_calls_correct_url(self) -> None:
        client = AgentForgeClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"task_id": "t-1", "status": "running"}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.get_task_status("t-1")

        assert result["status"] == "running"
        mock_http.get.assert_awaited_once_with("/api/v1/tasks/t-1")


class TestGetTaskResult:
    """获取任务结果测试。"""

    @pytest.mark.asyncio
    async def test_get_result_calls_correct_url(self) -> None:
        client = AgentForgeClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"task_id": "t-1", "result": {"score": 90}}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.get_task_result("t-1")

        assert result["result"]["score"] == 90
        mock_http.get.assert_awaited_once_with("/api/v1/tasks/t-1/result")


class TestCancelTask:
    """取消任务测试。"""

    @pytest.mark.asyncio
    async def test_cancel_calls_correct_url(self) -> None:
        client = AgentForgeClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"task_id": "t-1", "status": "cancelled"}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.cancel_task("t-1")

        assert result["status"] == "cancelled"
        mock_http.post.assert_awaited_once_with("/api/v1/tasks/t-1/cancel")


class TestListTasks:
    """查询任务列表测试。"""

    @pytest.mark.asyncio
    async def test_list_tasks_with_params(self) -> None:
        client = AgentForgeClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"tasks": [], "total": 0}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.list_tasks(status="pending", limit=10, offset=5)

        assert result["total"] == 0
        call_kwargs = mock_http.get.call_args
        params = call_kwargs[1]["params"]
        assert params["status"] == "pending"
        assert params["limit"] == 10
        assert params["offset"] == 5


class TestHealthCheck:
    """健康检查测试。"""

    @pytest.mark.asyncio
    async def test_health_check_calls_health_endpoint(self) -> None:
        client = AgentForgeClient()

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "healthy"}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)

        with patch.object(client, "_get_client", return_value=mock_http):
            result = await client.health_check()

        assert result["status"] == "healthy"
        mock_http.get.assert_awaited_once_with("/health")
