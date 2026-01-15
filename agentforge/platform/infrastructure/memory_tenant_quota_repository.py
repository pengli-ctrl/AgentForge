"""AgentForge 平台基础设施层：memory_tenant_quota_repository。

本模块提供 memory_tenant_quota_repository 的内存实现，用于单元测试、本地开发和离线验证。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：MemoryTenantQuotaRepository。
"""

from __future__ import annotations

from agentforge.platform.domain.tenant_quota import TenantQuota


class MemoryTenantQuotaRepository:
    """MemoryTenantQuotaRepository。

    MemoryTenantQuotaRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 upsert()。
    - 方法 get()。
    - 方法 list()。
    - 方法 delete()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._quotas: dict[str, TenantQuota] = {}

    async def upsert(self, quota: TenantQuota) -> None:
        """执行 upsert 对应的逻辑，并返回处理结果。

        Args:
            quota: TenantQuota，调用方传入的 quota 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._quotas[quota.tenant_id] = quota

    async def get(self, tenant_id: str) -> TenantQuota | None:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            TenantQuota | None，函数执行后的结果。
        """
        return self._quotas.get(tenant_id)

    async def list(self, limit: int = 100) -> list[TenantQuota]:
        """执行 list 对应的核心操作，并保持调用契约稳定。

        Args:
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[TenantQuota]，函数执行后的结果。
        """
        return list(self._quotas.values())[:limit]

    async def delete(self, tenant_id: str) -> None:
        """执行 delete 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._quotas.pop(tenant_id, None)
