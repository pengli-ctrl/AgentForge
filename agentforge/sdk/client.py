"""AgentForge SDK 客户端 — 提交任务、查询状态、获取结果。

封装 AgentForge API 的 HTTP 调用，提供 Pythonic 的 SDK 接口。

使用方式：
    client = AgentForgeClient(base_url="http://localhost:8000", api_key="...")
    task = await client.submit_task(
        workflow_name="code-review-pipeline",
        input_data={"code_content": "def add(a, b): return a + b"},
    )
    status = await client.get_task_status(task["task_id"])
    result = await client.get_task_result(task["task_id"])
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentForgeClient:
    """AgentForge SDK 客户端 — 封装 API 调用。

    提供同步和异步两种调用方式（本实现为异步）。
    底层使用 httpx 发送 HTTP 请求。

    Args:
        base_url: AgentForge API 基础 URL。
        api_key: API Key（认证用）。
        timeout: 请求超时时间（秒）。

    Example:
        >>> client = AgentForgeClient(
        ...     base_url="http://localhost:8000",
        ...     api_key="my-api-key",
        ... )
        >>> task = await client.submit_task(
        ...     workflow_name="code-review-pipeline",
        ...     input_data={"code_content": "print('hello')"},
        ... )
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str = "",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: Any = None

    async def _get_client(self) -> Any:
        """获取 HTTP 客户端实例（懒加载）。"""
        if self._client is None:
            try:
                import httpx

                headers: dict[str, str] = {}
                if self.api_key:
                    headers["X-API-Key"] = self.api_key

                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    headers=headers,
                    timeout=self.timeout,
                )
            except ImportError:
                logger.warning("httpx not installed, SDK HTTP calls unavailable")
                raise ImportError("httpx is required for AgentForgeClient")
        return self._client

    async def submit_task(
        self,
        workflow_name: str,
        input_data: dict[str, Any],
        priority: str = "task_primary",
    ) -> dict[str, Any]:
        """提交新任务。

        Args:
            workflow_name: 工作流名称。
            input_data: 任务输入数据。
            priority: 任务优先级。

        Returns:
            创建的任务信息。
        """
        client = await self._get_client()
        response = await client.post(
            "/api/v1/tasks",
            json={
                "workflow_name": workflow_name,
                "input_data": input_data,
                "priority": priority,
            },
        )
        response.raise_for_status()
        return response.json()

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        """查询任务状态。

        Args:
            task_id: 任务 ID。

        Returns:
            任务信息（含状态）。
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/tasks/{task_id}")
        response.raise_for_status()
        return response.json()

    async def get_task_result(self, task_id: str) -> dict[str, Any]:
        """获取任务结果。

        Args:
            task_id: 任务 ID。

        Returns:
            任务结果。
        """
        client = await self._get_client()
        response = await client.get(f"/api/v1/tasks/{task_id}/result")
        response.raise_for_status()
        return response.json()

    async def cancel_task(self, task_id: str) -> dict[str, Any]:
        """取消任务。

        Args:
            task_id: 任务 ID。

        Returns:
            取消后的任务信息。
        """
        client = await self._get_client()
        response = await client.post(f"/api/v1/tasks/{task_id}/cancel")
        response.raise_for_status()
        return response.json()

    async def list_tasks(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """查询任务列表。

        Args:
            status: 按状态过滤。
            limit: 返回数量上限。
            offset: 分页偏移量。

        Returns:
            任务列表和分页信息。
        """
        client = await self._get_client()
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status

        response = await client.get("/api/v1/tasks", params=params)
        response.raise_for_status()
        return response.json()

    async def list_agents(self) -> dict[str, Any]:
        """查询已注册的 Agent 列表。

        Returns:
            Agent 列表信息。
        """
        client = await self._get_client()
        response = await client.get("/api/v1/agents")
        response.raise_for_status()
        return response.json()

    async def get_metrics(self) -> str:
        """获取 Prometheus 指标数据。

        Returns:
            Prometheus 格式的指标文本。
        """
        client = await self._get_client()
        response = await client.get("/metrics")
        response.raise_for_status()
        return response.text

    async def health_check(self) -> dict[str, Any]:
        """服务健康检查。

        Returns:
            健康状态信息。
        """
        client = await self._get_client()
        response = await client.get("/health")
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        """关闭 HTTP 客户端连接。"""
        if self._client:
            await self._client.close()
            self._client = None
            logger.debug("AgentForgeClient connection closed")
