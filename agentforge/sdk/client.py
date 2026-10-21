"""客户端模块。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentForgeClient:
    """智能体相关组件。"""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str = "",
        timeout: float = 30.0,
    ) -> None:
        """初始化 AgentForgeClient。

        Args:
            base_url: 服务基础 URL。
            api_key: API键。
            timeout: 操作超时时间。
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: Any = None

    async def _get_client(self) -> Any:
        """获取客户端。

        Returns:
            处理结果对象。

        Raises:
            ImportError: 操作无法完成时抛出。
        """
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
            input_data: 输入数据。
            priority: 优先级。

        Returns:
            结构化结果字典。
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
            结构化结果字典。
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
            结构化结果字典。
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
            结构化结果字典。
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
            status: 目标状态。
            limit: 返回记录的最大数量。
            offset: 分页偏移量。

        Returns:
            结构化结果字典。
        """
        client = await self._get_client()
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status

        response = await client.get("/api/v1/tasks", params=params)
        response.raise_for_status()
        return response.json()

    async def list_agents(self) -> dict[str, Any]:
        """查询智能体。

        Returns:
            结构化结果字典。
        """
        client = await self._get_client()
        response = await client.get("/api/v1/agents")
        response.raise_for_status()
        return response.json()

    async def get_metrics(self) -> str:
        """读取指标。

        Returns:
            字符串结果。
        """
        client = await self._get_client()
        response = await client.get("/metrics")
        response.raise_for_status()
        return response.text

    async def health_check(self) -> dict[str, Any]:
        """服务健康检查。

        Returns:
            结构化结果字典。
        """
        client = await self._get_client()
        response = await client.get("/health")
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        """关闭智能体。"""
        if self._client:
            await self._client.close()
            self._client = None
            logger.debug("AgentForgeClient connection closed")
