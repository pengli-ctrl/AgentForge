"""AgentForge 平台领域模型层：rbac。

本模块定义 rbac 领域模型，约束业务状态、输入输出结构和跨层数据契约。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：Permission、Role、RoleAssignment。
- 主要函数：role_permissions。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Permission(str, Enum):
    """Permission。

    Permission 是状态或类型枚举，用于约束系统内部取值，避免使用散落的字符串常量。

    主要成员：
    - TICKET_READ: 'ticket.read'。
    - TICKET_REVIEW: 'ticket.review'。
    - TICKET_APPROVE: 'ticket.approve'。
    - TICKET_REPLY: 'ticket.reply'。
    - TICKET_WRITEBACK: 'ticket.writeback'。
    - KNOWLEDGE_READ: 'knowledge.read'。
    - KNOWLEDGE_WRITE: 'knowledge.write'。
    - CONNECTOR_READ: 'connector.read'。
    - CONNECTOR_MANAGE: 'connector.manage'。
    - AUDIT_READ: 'audit.read'。
    - ADMIN: 'admin.*'。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
    TICKET_READ = "ticket.read"
    TICKET_REVIEW = "ticket.review"
    TICKET_APPROVE = "ticket.approve"
    TICKET_REPLY = "ticket.reply"
    TICKET_WRITEBACK = "ticket.writeback"
    # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
    KNOWLEDGE_READ = "knowledge.read"
    KNOWLEDGE_WRITE = "knowledge.write"
    # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
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


def role_permissions(role: str) -> set[Permission]:
    """执行 role_permissions 对应的逻辑，并返回处理结果。

    Args:
        role: str，调用方传入的 role 参数。

    Returns:
        set[Permission]，函数执行后的结果。
    """
    return set(_ROLE_PERMISSIONS.get(role, set()))


class Role(BaseModel):
    """Role。

    Role 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - role_id: str。
    - tenant_id: str。
    - name: str。
    - description: str。
    - permissions: list[Permission]。
    - built_in: bool。
    - created_at: datetime。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    role_id: str
    tenant_id: str
    name: str
    description: str = ""
    permissions: list[Permission] = Field(default_factory=list)
    built_in: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoleAssignment(BaseModel):
    """RoleAssignment。

    RoleAssignment 是结构化数据模型，负责承载输入、输出或持久化数据，并执行字段级校验。

    主要成员：
    - model_config: ConfigDict(extra='forbid')。
    - assignment_id: str。
    - tenant_id: str。
    - user_id: str。
    - role_id: str。
    - granted_at: datetime。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    model_config = ConfigDict(extra="forbid")

    assignment_id: str
    tenant_id: str
    user_id: str
    role_id: str
    granted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
