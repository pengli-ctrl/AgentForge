"""AgentForge 平台基础设施层：memory_rbac_repository。

本模块提供 memory_rbac_repository 的内存实现，用于单元测试、本地开发和离线验证。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：MemoryRbacRepository。
"""

from __future__ import annotations

from agentforge.platform.domain.rbac import Role, RoleAssignment


class MemoryRbacRepository:
    """MemoryRbacRepository。

    MemoryRbacRepository 负责数据读写，并确保租户隔离、事务一致性和持久化细节不泄漏到应用层。

    主要成员：
    - 方法 save_role()。
    - 方法 get_role()。
    - 方法 list_roles()。
    - 方法 save_assignment()。
    - 方法 list_assignments()。
    - 方法 assignments_for_user()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._roles: dict[str, Role] = {}
        self._assignments: dict[str, RoleAssignment] = {}

    async def save_role(self, role: Role) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            role: Role，调用方传入的 role 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._roles[role.role_id] = role

    async def get_role(self, tenant_id: str, role_id: str) -> Role | None:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            role_id: str，调用方传入的 role_id 参数。

        Returns:
            Role | None，函数执行后的结果。
        """
        role = self._roles.get(role_id)
        if role is not None and role.tenant_id == tenant_id:
            return role
        return None

    async def list_roles(self, tenant_id: str) -> list[Role]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            list[Role]，函数执行后的结果。
        """
        return [r for r in self._roles.values() if r.tenant_id == tenant_id]

    async def save_assignment(self, assignment: RoleAssignment) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            assignment: RoleAssignment，调用方传入的 assignment 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._assignments[assignment.assignment_id] = assignment

    async def list_assignments(self, tenant_id: str) -> list[RoleAssignment]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            list[RoleAssignment]，函数执行后的结果。
        """
        return [a for a in self._assignments.values() if a.tenant_id == tenant_id]

    async def assignments_for_user(
        self,
        tenant_id: str,
        user_id: str,
    ) -> list[RoleAssignment]:
        """执行 assignments_for_user 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            user_id: str，调用方传入的 user_id 参数。

        Returns:
            list[RoleAssignment]，函数执行后的结果。
        """
        return [
            a
            for a in self._assignments.values()
            if a.tenant_id == tenant_id and a.user_id == user_id
        ]
