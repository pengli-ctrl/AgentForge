from __future__ import annotations

from agentforge.platform.domain.rbac import Role, RoleAssignment


class MemoryRbacRepository:
    """In-memory RBAC repository (role + assignment) for testing/dev."""

    def __init__(self) -> None:
        self._roles: dict[str, Role] = {}
        self._assignments: dict[str, RoleAssignment] = {}

    async def save_role(self, role: Role) -> None:
        self._roles[role.role_id] = role

    async def get_role(self, tenant_id: str, role_id: str) -> Role | None:
        role = self._roles.get(role_id)
        if role is not None and role.tenant_id == tenant_id:
            return role
        return None

    async def list_roles(self, tenant_id: str) -> list[Role]:
        return [r for r in self._roles.values() if r.tenant_id == tenant_id]

    async def save_assignment(self, assignment: RoleAssignment) -> None:
        self._assignments[assignment.assignment_id] = assignment

    async def list_assignments(self, tenant_id: str) -> list[RoleAssignment]:
        return [a for a in self._assignments.values() if a.tenant_id == tenant_id]

    async def assignments_for_user(
        self,
        tenant_id: str,
        user_id: str,
    ) -> list[RoleAssignment]:
        return [
            a
            for a in self._assignments.values()
            if a.tenant_id == tenant_id and a.user_id == user_id
        ]
