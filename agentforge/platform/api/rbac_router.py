"""AgentForge 平台 API 层：rbac_router。

本模块定义 rbac_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_rbac_router。
"""

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
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        rbac_repository: Any，调用方传入的 rbac_repository 参数。
        policy_engine: PolicyEngine | None，调用方传入的 policy_engine 参数。

    Returns:
        APIRouter，函数执行后的结果。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
    """
    if rbac_repository is None:
        rbac_repository = MemoryRbacRepository()
    router = APIRouter(prefix="/v1/rbac", tags=["rbac"])

    @router.post("/roles")
    async def create_role(tenant_id: str, name: str, description: str = "") -> dict:
        """创建新的业务对象，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            name: str，调用方传入的 name 参数。
            description: str，调用方传入的 description 参数。

        Returns:
            dict，函数执行后的结果。
        """
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。
        """
        roles = await rbac_repository.list_roles(tenant_id)
        return {"roles": [r.model_dump(mode="json") for r in roles]}

    @router.post("/roles/{role_id}/permissions")
    async def set_role_permissions(
        role_id: str,
        tenant_id: str,
        body: dict[str, Any],
    ) -> dict:
        """执行 set_role_permissions 对应的逻辑，并返回处理结果。

        Args:
            role_id: str，调用方传入的 role_id 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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
        """执行 assign_role 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            user_id: str，调用方传入的 user_id 参数。
            role_id: str，调用方传入的 role_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            user_id: str | None，调用方传入的 user_id 参数。

        Returns:
            dict，函数执行后的结果。
        """
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
        """执行 authorize 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            principal: str，调用方传入的 principal 参数。
            action: str，调用方传入的 action 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
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
