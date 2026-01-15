"""AgentForge 平台应用服务层：builtin_policies。

本模块负责 builtin_policies 相关的平台能力，是 平台应用服务层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：builtin_policies、seed_rbac。
"""

from __future__ import annotations

from agentforge.platform.domain.policy import ActionPolicy
from agentforge.platform.domain.rbac import Permission, Role


def builtin_policies() -> list[ActionPolicy]:
    """执行 builtin_policies 对应的逻辑，并返回处理结果。

    Returns:
        list[ActionPolicy]，函数执行后的结果。
    """
    return [
        ActionPolicy(
            name="ticket_writeback",
            tenant_id="*",
            action="ticket.writeback",
            risk_level="high",
            required_permission="ticket.writeback",
            require_approval=True,
            allowed_roles=[],
            enabled=True,
        ),
        ActionPolicy(
            name="ticket_view",
            tenant_id="*",
            action="ticket.view",
            risk_level="low",
            required_permission="ticket.read",
            require_approval=False,
            allowed_roles=[],
            enabled=True,
        ),
    ]


def _async_relation_check(openfga_client):
    """执行 _async_relation_check 对应的逻辑，并返回处理结果。

    Args:
        openfga_client: Any，调用方传入的 openfga_client 参数。

    Returns:
        None，函数执行后的结果。
    """

    async def _check(tuple_) -> bool:
        """执行 _check 对应的逻辑，并返回处理结果。

        Args:
            tuple_: Any，调用方传入的 tuple_ 参数。

        Returns:
            bool，函数执行后的结果。
        """
        return openfga_client.acheck(
            tuple_.tenant_id,
            tuple_.object_type,
            tuple_.object_id,
            tuple_.relation,
            tuple_.subject_id,
        )

    return _check


async def seed_rbac(repository) -> None:
    """执行 seed_rbac 对应的逻辑，并返回处理结果。

    Args:
        repository: Any，调用方传入的 repository 参数。

    Returns:
        None，函数执行后的结果。
    """
    roles = [
        Role(
            role_id="role-support-admin",
            tenant_id="*",
            name="support_admin",
            description="Tenant admin with full ticket and write-back rights.",
            permissions=[
                Permission.TICKET_READ,
                Permission.TICKET_WRITEBACK,
                Permission.TICKET_APPROVE,
                Permission.CONNECTOR_MANAGE,
            ],
            built_in=True,
        ),
        Role(
            role_id="role-support-agent",
            tenant_id="*",
            name="support_agent",
            description="Support agent who can view and draft replies.",
            permissions=[Permission.TICKET_READ, Permission.TICKET_REPLY],
            built_in=True,
        ),
    ]
    existing = await repository.list_roles("*")
    if existing:
        return
    for role in roles:
        await repository.save_role(role)
