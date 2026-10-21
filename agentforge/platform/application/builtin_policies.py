"""内置策略模块。"""

from __future__ import annotations

from agentforge.platform.domain.policy import ActionPolicy
from agentforge.platform.domain.rbac import Permission, Role


def builtin_policies() -> list[ActionPolicy]:
    """处理内置策略。

    Returns:
        结果列表。
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
            name="expense_claim_approve",
            tenant_id="*",
            action="expense.claim.approve",
            risk_level="high",
            required_permission="expense.claim.approve",
            require_approval=False,
            allowed_roles=[],
            enabled=True,
        ),
        ActionPolicy(
            name="expense_claim_reject",
            tenant_id="*",
            action="expense.claim.reject",
            risk_level="high",
            required_permission="expense.claim.approve",
            require_approval=False,
            allowed_roles=[],
            enabled=True,
        ),
        ActionPolicy(
            name="expense_ledger_writeback",
            tenant_id="*",
            action="expense.ledger.writeback",
            risk_level="high",
            required_permission="expense.ledger.writeback",
            require_approval=False,
            allowed_roles=[],
            enabled=True,
        ),
        ActionPolicy(
            name="expense_ledger_verify",
            tenant_id="*",
            action="expense.ledger.verify",
            risk_level="medium",
            required_permission="expense.ledger.verify",
            require_approval=False,
            allowed_roles=[],
            enabled=True,
        ),
        ActionPolicy(
            name="expense_ledger_compensate",
            tenant_id="*",
            action="expense.ledger.compensate",
            risk_level="high",
            required_permission="expense.ledger.compensate",
            require_approval=False,
            allowed_roles=[],
            enabled=True,
        ),
        ActionPolicy(
            name="expense_invoice_write",
            tenant_id="*",
            action="expense.invoice.write",
            risk_level="medium",
            required_permission="expense.invoice.write",
            require_approval=False,
            allowed_roles=[],
            enabled=True,
        ),
        ActionPolicy(
            name="expense_invoice_verify",
            tenant_id="*",
            action="expense.invoice.verify",
            risk_level="medium",
            required_permission="expense.invoice.verify",
            require_approval=False,
            allowed_roles=[],
            enabled=True,
        ),
        ActionPolicy(
            name="expense_invoice_release",
            tenant_id="*",
            action="expense.invoice.release",
            risk_level="high",
            required_permission="expense.invoice.release",
            require_approval=False,
            allowed_roles=[],
            enabled=True,
        ),
        ActionPolicy(
            name="expense_invoice_override",
            tenant_id="*",
            action="expense.invoice.override",
            risk_level="high",
            required_permission="expense.invoice.override",
            require_approval=False,
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
    """处理异步关系检查。

    Args:
        openfga_client: 客户端。

    Returns:
        处理结果。
    """

    async def _check(tuple_) -> bool:
        """执行内部一致性检查。

        Args:
            tuple_: 输入参数。

        Returns:
            操作是否成功。
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
    """初始化RBAC。

    Args:
        repository: 数据仓储实现。
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
            role_id="role-finance-approver",
            tenant_id="*",
            name="finance_approver",
            description="Finance approver for expense claims and ledger access.",
            permissions=[
                "expense.claim.read",
                "expense.claim.approve",
                "expense.ledger.writeback",
                "expense.ledger.verify",
                "expense.ledger.compensate",
                "expense.invoice.read",
                "expense.invoice.write",
                "expense.invoice.verify",
                "expense.invoice.release",
                "expense.invoice.override",
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
    by_id = {role.role_id: role for role in existing}
    for role in roles:
        current = by_id.get(role.role_id)
        if current is None:
            await repository.save_role(role)
            continue
        merged_permissions = list(dict.fromkeys([*current.permissions, *role.permissions]))
        if merged_permissions != current.permissions:
            current.permissions = merged_permissions
            await repository.save_role(current)
