"""AgentForge 平台基础设施层：client。

本模块负责 client 相关的平台能力，是 平台基础设施层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：TemporalWorkflowClient。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import uuid4

from temporalio.client import Client

from agentforge.platform.workflows.support_ticket import SupportTicketWorkflow


class TemporalWorkflowClient:
    """TemporalWorkflowClient。

    TemporalWorkflowClient 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

    主要成员：
    - 方法 start_support_workflow()。
    - 方法 signal_approval()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        address: str,
        namespace: str,
        task_queue: str = "support-copilot",
        client_factory: Callable[..., Awaitable[Client]] | None = None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            address: str，调用方传入的 address 参数。
            namespace: str，调用方传入的 namespace 参数。
            task_queue: str，调用方传入的 task_queue 参数。
            client_factory: Callable[..., Awaitable[Client]] | None，调用方传入的 client_factory 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._address = address
        self._namespace = namespace
        self._task_queue = task_queue
        self._client_factory = client_factory or Client.connect
        self._client: Client | None = None

    async def _get_client(self) -> Client:
        """执行 _get_client 对应的逻辑，并返回处理结果。

        Returns:
            Client，函数执行后的结果。
        """
        if self._client is None:
            self._client = await self._client_factory(
                self._address,
                namespace=self._namespace,
            )
        return self._client

    async def start_support_workflow(self, event: dict, workflow_id: str | None = None) -> str:
        """执行 start_support_workflow 对应的逻辑，并返回处理结果。

        Args:
            event: dict，调用方传入的 event 参数。
            workflow_id: str | None，调用方传入的 workflow_id 参数。

        Returns:
            str，函数执行后的结果。
        """
        client = await self._get_client()
        resolved_id = workflow_id or f"support-{uuid4()}"
        await client.start_workflow(
            SupportTicketWorkflow.run,
            event,
            id=resolved_id,
            task_queue=self._task_queue,
        )
        return resolved_id

    async def signal_approval(
        self,
        workflow_id: str,
        decision: str,
        decided_by: str,
    ) -> None:
        """执行 signal_approval 对应的逻辑，并返回处理结果。

        Args:
            workflow_id: str，调用方传入的 workflow_id 参数。
            decision: str，调用方传入的 decision 参数。
            decided_by: str，调用方传入的 decided_by 参数。

        Returns:
            None，函数执行后的结果。
        """
        client = await self._get_client()
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal(
            SupportTicketWorkflow.approve,
            {"decision": decision, "decided_by": decided_by},
        )
