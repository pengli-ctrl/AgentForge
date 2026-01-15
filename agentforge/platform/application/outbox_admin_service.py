"""AgentForge 平台应用服务层：outbox_admin_service。

本模块实现 outbox_admin_service 应用服务，编排多个领域对象和基础设施组件完成业务流程。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：OutboxAdminService。
"""

from __future__ import annotations

from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore


class OutboxAdminService:
    """OutboxAdminService。

    OutboxAdminService 编排业务流程，协调仓储、模型、策略和外部连接器完成用例。

    主要成员：
    - 方法 list_failed()。
    - 方法 replay()。
    - 方法 replay_all()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, store: SQLAlchemyOutboxStore) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            store: SQLAlchemyOutboxStore，调用方传入的 store 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._store = store

    async def list_failed(self, limit: int = 100) -> list[dict]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[dict]，函数执行后的结果。
        """
        return await self._store.list_failed(limit=limit)

    async def replay(self, event_id: str) -> bool:
        """执行 replay 对应的逻辑，并返回处理结果。

        Args:
            event_id: str，调用方传入的 event_id 参数。

        Returns:
            bool，函数执行后的结果。
        """
        return await self._store.replay(event_id)

    async def replay_all(self, limit: int = 100) -> int:
        """执行 replay_all 对应的逻辑，并返回处理结果。

        Args:
            limit: int，调用方传入的 limit 参数。

        Returns:
            int，函数执行后的结果。
        """
        failed = await self._store.list_failed(limit=limit)
        replayed = 0
        for event in failed:
            if await self._store.replay(event["event_id"]):
                replayed += 1
        return replayed
