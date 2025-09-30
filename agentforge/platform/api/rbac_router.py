from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from agentforge.platform.application.policy_engine import PolicyEngine
from agentforge.platform.domain.rbac import Permission, Role, RoleAssignment
from agentforge.platform.infrastructure.memory_rbac_repository import MemoryRbacRepository


def create_rbac_router(
    rbac_repository=None,
    policy_engine: PolicyEngine | None = None,
) -> APIRouter:
    if rbac_repository is None:
        rbac_repository = MemoryRbacRepository()
    router = APIRouter(prefix="/v1/rbac", tags=["rbac"])

    @router.post("/roles")
    async def create_role(tenant_id: str, name: str, description: str = "") -> dict:
        role = Role(
            role_id=f"role-{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            name=name,
            description=description,
            permissions=[],
            built_in=False,
        )
        await rbac_repository.save_role(role)
        return role.model_dump(mode="json")

    @router.get("/roles")
    async def list_roles(tenant_id: str) -> dict:
        roles = await rbac_repository.list_roles(tenant_id)
        return {"roles": [r.model_dump(mode="json") for r in roles]}

    @router.post("/roles/{role_id}/permissions")
    async def set_role_permissions(
        role_id: str,
        tenant_id: str,
        body: dict[str, Any],
    ) -> dict:
        role = await rbac_repository.get_role(tenant_id, role_id)
        if role is None:
            raise HTTPException(status_code=404, detail="role not found")
        raw = body.get("permissions", [])
        try:
            role.permissions = [Permission(p) for p in raw]
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await rbac_repository.save_role(role)
        return role.model_dump(mode="json")

    @router.post("/assignments")
    async def assign_role(
        tenant_id: str,
        user_id: str,
        role_id: str,
    ) -> dict:
        role = await rbac_repository.get_role(tenant_id, role_id)
        if role is None:
            raise HTTPException(status_code=404, detail="role not found")
        assignment = RoleAssignment(
            assignment_id=f"asg-{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            user_id=user_id,
            role_id=role_id,
        )
        await rbac_repository.save_assignment(assignment)
        return assignment.model_dump(mode="json")

    @router.get("/assignments")
    async def list_assignments(tenant_id: str, user_id: str | None = None) -> dict:
        if user_id:
            assignments = await rbac_repository.assignments_for_user(tenant_id, user_id)
        else:
            assignments = await rbac_repository.list_assignments(tenant_id)
        return {"assignments": [a.model_dump(mode="json") for a in assignments]}

    @router.post("/authorize")
    async def authorize(
        tenant_id: str,
        principal: str,
        action: str,
        body: dict[str, Any],
    ) -> dict:
        if policy_engine is None:
            raise HTTPException(status_code=503, detail="policy engine not configured")
        assignments = await rbac_repository.assignments_for_user(tenant_id, principal)
        roles = []
        permissions = set()
        for assignment in assignments:
            role = await rbac_repository.get_role(tenant_id, assignment.role_id)
            if role is not None:
                roles.append(role.name or assignment.role_id)
                permissions |= set(role.permissions)
        decision = await policy_engine.authorize(
            tenant_id=tenant_id,
            principal=principal,
            action=action,
            roles=roles,
            permissions=list(permissions),
            resource_type=body.get("resource_type", ""),
            resource_id=body.get("resource_id", ""),
            relation=body.get("relation"),
        )
        return decision.model_dump(mode="json")

    return router
