"""高风险授权器测试模块。

本测试模块验证 test_high_risk_authorizer 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：_FakeAuditRepo、_FakeRegistry。
-
主要函数：test_approved_high_risk_allowed、test_unapproved_high_risk_denied、test_unauthorized_principa
    l_denied、test_audit_recorded_for_allow_and_deny、test_execute_guarded_denied_raises、test_writ
    eback_gate_blocks_unapproved、test_writeback_gate_allows_approved。
"""

import pytest

from agentforge.platform.application.builtin_policies import builtin_policies
from agentforge.platform.application.policy_engine import PolicyEngine
from agentforge.platform.domain.authorization import AuthorizationOutcome
from agentforge.platform.domain.rbac import Permission, Role, RoleAssignment
from agentforge.platform.infrastructure.memory_rbac_repository import MemoryRbacRepository
from agentforge.platform.modules.support.application.high_risk_authorizer import (
    HighRiskActionAuthorizer,
)
from agentforge.platform.modules.support.application.writeback import TicketWritebackService
from agentforge.platform.modules.support.domain.ticket import (
    RiskLevel,
    Ticket,
    TicketPriority,
    TicketStatus,
)


class _FakeAuditRepo:
    """模拟审计仓储相关组件。"""

    def __init__(self) -> None:
        """初始化模拟审计仓储。"""
        self.events: list = []

    async def save(self, event) -> None:  # noqa: ANN001
        """保存模拟审计仓储。

        Args:
            event: 待处理事件。
        """
        self.events.append(event)


class _FakeRegistry:
    """模拟注册表。"""

    def __init__(self) -> None:
        """初始化模拟。"""
        self.invocations: list = []
        spec = type(
            "S",
            (),
            {"connector_id": "conn-crm", "enabled": True, "allowed_actions": ["writeback"]},
        )()
        self.specs = [spec]

    async def invoke(self, connector_id, action, payload, context):  # noqa: ANN001
        """调用模拟。

        Args:
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            payload: 事件、工作流或请求载荷。
            context: 执行上下文。

        Returns:
            处理结果。
        """
        self.invocations.append((connector_id, action, context.idempotency_key))
        return type("R", (), {"ok": True, "error": None, "data": {"ok": True}})()

    def list_specs(self, tenant_id):  # noqa: ANN001
        """查询规格。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            处理结果。
        """
        return self.specs


def _ticket(status: TicketStatus = TicketStatus.READY_TO_PUBLISH) -> Ticket:
    """处理工单。

    Args:
        status: 目标状态。

    Returns:
        工单结果。
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
    """处理授权器使用管理。

    Args:
        record: 待处理的领域记录。

    Returns:
        高风险操作授权器结果。
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
    """验证已批准高风险允许对应的测试场景。"""
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
    """验证未批准高风险拒绝对应的测试场景。"""
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
    """验证未授权拒绝对应的测试场景。"""
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
    """验证审计已记录用于允许及对应的测试场景。"""
    rbac = MemoryRbacRepository()
    audit = _FakeAuditRepo()
    engine = PolicyEngine(policies=builtin_policies())
    auth = HighRiskActionAuthorizer(engine, audit, rbac)
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
    assert any(e.payload["outcome"] == "denied" for e in audit.events)


@pytest.mark.asyncio
async def test_execute_guarded_denied_raises() -> None:
    """验证执行拒绝抛出对应的测试场景。"""
    auth = await _authorizer_with_admin()

    async def _fn():
        """处理函数。

        Raises:
            AssertionError: 操作无法完成时抛出。
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
    """验证写回门禁阻止未批准对应的测试场景。"""
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
    """验证写回门禁允许已批准对应的测试场景。"""
    registry = _FakeRegistry()
    auth = await _authorizer_with_admin()
    service = TicketWritebackService(
        registry, audit_repository=_FakeAuditRepo(), high_risk_authorizer=auth
    )
    data = await service.write_back(_ticket(TicketStatus.READY_TO_PUBLISH), actor="alice")
    assert data == {"ok": True}
    assert len(registry.invocations) == 1
