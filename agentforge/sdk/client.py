"""AgentForge SDK 层：client。

本模块负责 client 相关能力，是 SDK 层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要类：AgentForgeClient。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AgentForgeClient:
    """AgentForgeClient。

    AgentForgeClient 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

    主要成员：
    - 方法 submit_task()。
    - 方法 get_task_status()。
    - 方法 get_task_result()。
    - 方法 cancel_task()。
    - 方法 list_tasks()。
    - 方法 list_agents()。
    - 方法 get_metrics()。
    - 方法 health_check()。
    - 方法 close()。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str = "",
        timeout: float = 30.0,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            base_url: str，调用方传入的 base_url 参数。
            api_key: str，调用方传入的 api_key 参数。
            timeout: float，调用方传入的 timeout 参数。

        Returns:
            None，函数执行后的结果。
        """
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
