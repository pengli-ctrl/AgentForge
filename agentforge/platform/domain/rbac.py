"""RBAC模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Permission(str, Enum):
    """权限枚举。"""

    TICKET_READ = "ticket.read"
    TICKET_REVIEW = "ticket.review"
    TICKET_APPROVE = "ticket.approve"
    TICKET_REPLY = "ticket.reply"
    TICKET_WRITEBACK = "ticket.writeback"
    KNOWLEDGE_READ = "knowledge.read"
    KNOWLEDGE_WRITE = "knowledge.write"
    CONNECTOR_READ = "connector.read"
    CONNECTOR_MANAGE = "connector.manage"
    # 验证审计记录，确保关键行为可追踪。
    AUDIT_READ = "audit.read"
    # 验证管理员权限和边界行为。
    ADMIN = "admin.*"


# 常量：_ROLE_PERMISSIONS。
_ROLE_PERMISSIONS: dict[str, set[Permission]] = {
    "admin": {
        Permission.ADMIN,
        Permission.TICKET_READ,
        Permission.TICKET_REVIEW,
        Permission.TICKET_APPROVE,
        Permission.TICKET_REPLY,
        Permission.TICKET_WRITEBACK,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.CONNECTOR_READ,
        Permission.CONNECTOR_MANAGE,
        Permission.AUDIT_READ,
    },
    "agent": {
        Permission.TICKET_READ,
        Permission.TICKET_REVIEW,
        Permission.TICKET_REPLY,
        Permission.KNOWLEDGE_READ,
        Permission.CONNECTOR_READ,
    },
    "supervisor": {
        Permission.TICKET_READ,
        Permission.TICKET_APPROVE,
        Permission.AUDIT_READ,
        Permission.KNOWLEDGE_READ,
    },
    "auditor": {
        Permission.AUDIT_READ,
        Permission.TICKET_READ,
        Permission.CONNECTOR_READ,
    },
}


def role_permissions(role: str) -> set[str]:
    """处理角色权限。

    Args:
        role: 角色。

    Returns:
        设置结果。
    """
    return {permission.value for permission in _ROLE_PERMISSIONS.get(role, set())}


class Role(BaseModel):
    """角色领域组件。

    Attributes:
        role_id: 角色ID。
        tenant_id: 租户 ID，用于数据隔离。
        name: 名称。
        description: 描述信息。
        permissions: 权限。
        built_in: 在。
        created_at: 创建时间。
    """

    model_config = ConfigDict(extra="forbid")

    role_id: str
    tenant_id: str
    name: str
    description: str = ""
    permissions: list[str] = Field(default_factory=list)
    built_in: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoleAssignment(BaseModel):
    """角色分配相关组件。

    Attributes:
        assignment_id: 分配ID。
        tenant_id: 租户 ID，用于数据隔离。
        user_id: 用户ID。
        role_id: 角色ID。
        granted_at: 于。
    """

    model_config = ConfigDict(extra="forbid")

    assignment_id: str
    tenant_id: str
    user_id: str
    role_id: str
    granted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
