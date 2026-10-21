"""记忆RBAC仓储模块。"""

from __future__ import annotations

from agentforge.platform.domain.rbac import Role, RoleAssignment


class MemoryRbacRepository:
    """RBAC仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryRbacRepository。"""
        self._roles: dict[str, Role] = {}
        self._assignments: dict[str, RoleAssignment] = {}

    async def save_role(self, role: Role) -> None:
        """保存角色。

        Args:
            role: 角色。
        """
        self._roles[role.role_id] = role

    async def get_role(self, tenant_id: str, role_id: str) -> Role | None:
        """读取角色。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            role_id: 角色 ID。

        Returns:
            角色无结果。
        """
        role = self._roles.get(role_id)
        if role is not None and role.tenant_id == tenant_id:
            return role
        return None

    async def list_roles(self, tenant_id: str) -> list[Role]:
        """查询角色。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        return [r for r in self._roles.values() if r.tenant_id == tenant_id]

    async def save_assignment(self, assignment: RoleAssignment) -> None:
        """保存分配。

        Args:
            assignment: 分配。
        """
        self._assignments[assignment.assignment_id] = assignment

    async def list_assignments(self, tenant_id: str) -> list[RoleAssignment]:
        """查询分配记录。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        return [a for a in self._assignments.values() if a.tenant_id == tenant_id]

    async def assignments_for_user(
        self,
        tenant_id: str,
        user_id: str,
    ) -> list[RoleAssignment]:
        """获取用户的分配记录。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            user_id: 用户 ID。

        Returns:
            结果列表。
        """
        return [
            a
            for a in self._assignments.values()
            if a.tenant_id == tenant_id and a.user_id == user_id
        ]
