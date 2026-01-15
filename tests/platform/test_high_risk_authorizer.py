"""AgentForge 平台测试层：test_high_risk_authorizer。

本测试模块验证 test_high_risk_authorizer 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：_FakeAuditRepo、_FakeRegistry。
-
主要函数：test_approved_high_risk_allowed、test_unapproved_high_risk_denied、test_unauthorized_principal_denied、test_audit_recorded_for_allow_and_deny、test_execute_guarded_denied_raises、test_writeback_gate_blocks_unapproved、test_writeback_gate_allows_approved。
"""

import pytest

from agentforge.platform.application.builtin_policies import builtin_policies
from agentforge.platform.application.high_risk_authorizer import HighRiskActionAuthorizer
from agentforge.platform.application.policy_engine import PolicyEngine
from agentforge.platform.application.ticket_writeback import TicketWritebackService
from agentforge.platform.domain.authorization import AuthorizationOutcome
from agentforge.platform.domain.rbac import Permission, Role, RoleAssignment
from agentforge.platform.domain.ticket import (
    RiskLevel,
    Ticket,
    TicketPriority,
    TicketStatus,
)
from agentforge.platform.infrastructure.memory_rbac_repository import MemoryRbacRepository


class _FakeAuditRepo:
    """_FakeAuditRepo。

    _FakeAuditRepo 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 save()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self.events: list = []

    async def save(self, event) -> None:  # noqa: ANN001
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            event: Any，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.events.append(event)


class _FakeRegistry:
    """_FakeRegistry。

    _FakeRegistry 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 invoke()。
    - 方法 list_specs()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self.invocations: list = []
        spec = type(
            "S",
            (),
            {"connector_id": "conn-crm", "enabled": True, "allowed_actions": ["writeback"]},
        )()
        self.specs = [spec]

    async def invoke(self, connector_id, action, payload, context):  # noqa: ANN001
        """执行 invoke 对应的逻辑，并返回处理结果。

        Args:
            connector_id: Any，调用方传入的 connector_id 参数。
            action: Any，调用方传入的 action 参数。
            payload: Any，调用方传入的 payload 参数。
            context: Any，调用方传入的 context 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.invocations.append((connector_id, action, context.idempotency_key))
        return type("R", (), {"ok": True, "error": None, "data": {"ok": True}})()

    def list_specs(self, tenant_id):  # noqa: ANN001
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: Any，调用方传入的 tenant_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        return self.specs


def _ticket(status: TicketStatus = TicketStatus.READY_TO_PUBLISH) -> Ticket:
    """执行 _ticket 对应的逻辑，并返回处理结果。

    Args:
        status: TicketStatus，调用方传入的 status 参数。

    Returns:
        Ticket，函数执行后的结果。
    """
    metadata = {}
    if status == TicketStatus.READY_TO_PUBLISH:
        metadata["approval"] = {"decision": "approve", "decided_by": "manager-1"}
    return Ticket(
        ticket_id="ticket-hr-1",
        tenant_id="t1",
        customer_id="cust-1",
        conversation_id="conv-1",
        source="feishu",
        subject="Refund",
        status=status,
        priority=TicketPriority.P1,
        intent="refund",
        risk_level=RiskLevel.HIGH,
        idempotency_key="ik-hr-1",
        metadata=metadata,
    )


async def _authorizer_with_admin(record: bool = True) -> HighRiskActionAuthorizer:
    """执行 _authorizer_with_admin 对应的逻辑，并返回处理结果。

    Args:
        record: bool，调用方传入的 record 参数。

    Returns:
        HighRiskActionAuthorizer，函数执行后的结果。
    """
    rbac = MemoryRbacRepository()
    await rbac.save_role(
        Role(
            role_id="r-admin",
            tenant_id="t1",
            name="support_admin",
            description="",
            permissions=[Permission.TICKET_WRITEBACK, Permission.TICKET_READ],
            built_in=True,
        )
    )
    await rbac.save_assignment(
        RoleAssignment(
            assignment_id="asg-1",
            tenant_id="t1",
            user_id="alice",
            role_id="r-admin",
        )
    )
    engine = PolicyEngine(policies=builtin_policies())
    return HighRiskActionAuthorizer(
        engine,
        audit_repository=_FakeAuditRepo(),
        rbac_repository=rbac,
    )


@pytest.mark.asyncio
async def test_approved_high_risk_allowed() -> None:
    """验证 approved_high_risk_allowed 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    auth = await _authorizer_with_admin()
    decision = await auth.authorize(
        tenant_id="t1",
        principal="alice",
        action="ticket.writeback",
        resource_type="ticket",
        resource_id="ticket-hr-1",
        ticket=_ticket(TicketStatus.READY_TO_PUBLISH),
    )
    assert decision.outcome == AuthorizationOutcome.ALLOWED
    assert decision.approval_ref == "manager-1"
    assert "human approval granted" in decision.reasons


@pytest.mark.asyncio
async def test_unapproved_high_risk_denied() -> None:
    """验证 unapproved_high_risk_denied 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    auth = await _authorizer_with_admin()
    decision = await auth.authorize(
        tenant_id="t1",
        principal="alice",
        action="ticket.writeback",
        resource_type="ticket",
        resource_id="ticket-hr-1",
        ticket=_ticket(TicketStatus.WAITING_APPROVAL),
    )
    assert decision.outcome == AuthorizationOutcome.DENIED
    assert "human approval required but not granted" in decision.reasons


@pytest.mark.asyncio
async def test_unauthorized_principal_denied() -> None:
    """验证 unauthorized_principal_denied 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    auth = await _authorizer_with_admin()
    decision = await auth.authorize(
        tenant_id="t1",
        principal="mallory",
        action="ticket.writeback",
        resource_type="ticket",
        resource_id="ticket-hr-1",
        ticket=_ticket(TicketStatus.READY_TO_PUBLISH),
    )
    assert decision.outcome == AuthorizationOutcome.DENIED


@pytest.mark.asyncio
async def test_audit_recorded_for_allow_and_deny() -> None:
    """验证 audit_recorded_for_allow_and_deny 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    rbac = MemoryRbacRepository()
    audit = _FakeAuditRepo()
    engine = PolicyEngine(policies=builtin_policies())
    auth = HighRiskActionAuthorizer(engine, audit, rbac)
    # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
    await auth.authorize(
        tenant_id="t1",
        principal="nobody",
        action="ticket.writeback",
        resource_type="ticket",
        resource_id="x",
        ticket=_ticket(TicketStatus.WAITING_APPROVAL),
    )
    actions = [e.action for e in audit.events]
    assert "ticket.writeback.authorization" in actions
    # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
    assert any(e.payload["outcome"] == "denied" for e in audit.events)


@pytest.mark.asyncio
async def test_execute_guarded_denied_raises() -> None:
    """验证 execute_guarded_denied_raises 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。

    Raises:
        AssertionError: 当输入、状态或外部依赖不满足要求时抛出。
    """
    auth = await _authorizer_with_admin()

    async def _fn():
        """执行 _fn 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。

        Raises:
            AssertionError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        raise AssertionError("should not be called")

    with pytest.raises(PermissionError):
        await auth.execute_guarded(
            tenant_id="t1",
            principal="alice",
            action="ticket.writeback",
            resource_type="ticket",
            resource_id="x",
            ticket=_ticket(TicketStatus.WAITING_APPROVAL),
            fn=_fn,
        )


@pytest.mark.asyncio
async def test_writeback_gate_blocks_unapproved() -> None:
    """验证 writeback_gate_blocks_unapproved 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    registry = _FakeRegistry()
    auth = await _authorizer_with_admin()
    service = TicketWritebackService(
        registry, audit_repository=_FakeAuditRepo(), high_risk_authorizer=auth
    )
    with pytest.raises(PermissionError):
        await service.write_back(_ticket(TicketStatus.WAITING_APPROVAL), actor="alice")
    assert registry.invocations == []


@pytest.mark.asyncio
async def test_writeback_gate_allows_approved() -> None:
    """验证 writeback_gate_allows_approved 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    registry = _FakeRegistry()
    auth = await _authorizer_with_admin()
    service = TicketWritebackService(
        registry, audit_repository=_FakeAuditRepo(), high_risk_authorizer=auth
    )
    data = await service.write_back(_ticket(TicketStatus.READY_TO_PUBLISH), actor="alice")
    assert data == {"ok": True}
    assert len(registry.invocations) == 1
