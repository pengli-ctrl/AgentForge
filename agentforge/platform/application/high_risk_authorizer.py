"""AgentForge 平台应用服务层：high_risk_authorizer。

本模块负责 high_risk_authorizer 相关的平台能力，是 平台应用服务层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：HighRiskActionAuthorizer。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from agentforge.platform.application.policy_engine import PolicyEngine
from agentforge.platform.application.ports import AuditRepository
from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.authorization import (
    AuthorizationDecision,
    AuthorizationOutcome,
)
from agentforge.platform.domain.ticket import RiskLevel, Ticket, TicketStatus
from agentforge.platform.infrastructure.memory_rbac_repository import MemoryRbacRepository


class HighRiskActionAuthorizer:
    """HighRiskActionAuthorizer。

    HighRiskActionAuthorizer 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 authorize()。
    - 方法 execute_guarded()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        policy_engine: PolicyEngine,
        audit_repository: AuditRepository | None = None,
        rbac_repository=None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            policy_engine: PolicyEngine，调用方传入的 policy_engine 参数。
            audit_repository: AuditRepository | None，调用方传入的 audit_repository 参数。
            rbac_repository: Any，调用方传入的 rbac_repository 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._policy_engine = policy_engine
        self._audit_repository = audit_repository
        if rbac_repository is None:
            rbac_repository = MemoryRbacRepository()
        self._rbac_repository = rbac_repository

    async def authorize(
        self,
        *,
        tenant_id: str,
        principal: str,
        action: str,
        resource_type: str,
        resource_id: str,
        ticket: Ticket | None = None,
        relation: str | None = None,
        record: bool = True,
    ) -> AuthorizationDecision:
        """执行 authorize 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            principal: str，调用方传入的 principal 参数。
            action: str，调用方传入的 action 参数。
            resource_type: str，调用方传入的 resource_type 参数。
            resource_id: str，调用方传入的 resource_id 参数。
            ticket: Ticket | None，调用方传入的 ticket 参数。
            relation: str | None，调用方传入的 relation 参数。
            record: bool，调用方传入的 record 参数。

        Returns:
            AuthorizationDecision，函数执行后的结果。
        """
        roles, permissions = await self._resolve_identity(tenant_id, principal)

        policy_decision = await self._policy_engine.authorize(
            tenant_id=tenant_id,
            principal=principal,
            action=action,
            roles=roles,
            permissions=permissions,
            resource_type=resource_type,
            resource_id=resource_id,
            relation=relation,
        )

        outcome_map = {
            "allowed": AuthorizationOutcome.ALLOWED,
            "denied": AuthorizationOutcome.DENIED,
            "requires_approval": AuthorizationOutcome.REQUIRES_APPROVAL,
        }
        outcome = outcome_map.get(policy_decision.outcome.value, AuthorizationOutcome.DENIED)

        approval_ref = None
        reasons = list(policy_decision.reasons)
        # 验证审批边界，确保高风险动作必须经过审批。
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        if outcome == AuthorizationOutcome.REQUIRES_APPROVAL:
            granted = self._approval_granted(ticket)
            if granted:
                outcome = AuthorizationOutcome.ALLOWED
                approval_ref = granted
                reasons.append("human approval granted")
            else:
                outcome = AuthorizationOutcome.DENIED
                reasons.append("human approval required but not granted")

        decision = AuthorizationDecision(
            authorization_id=f"authz-{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            principal=principal,
            outcome=outcome,
            reasons=reasons,
            approval_ref=approval_ref,
        )

        if record:
            await self._record_audit(tenant_id, decision, ticket)
        return decision

    @staticmethod
    def _approval_granted(ticket: Ticket | None) -> str | None:
        """执行 _approval_granted 对应的逻辑，并返回处理结果。

        Args:
            ticket: Ticket | None，调用方传入的 ticket 参数。

        Returns:
            str | None，函数执行后的结果。
        """
        if ticket is None:
            return None
        if ticket.status != TicketStatus.READY_TO_PUBLISH:
            return None
        approval = ticket.metadata.get("approval") or {}
        if approval.get("decision") != "approve":
            return None
        return approval.get("decided_by") or ticket.ticket_id

    async def _resolve_identity(self, tenant_id: str, principal: str) -> tuple[list[str], list]:
        """执行 _resolve_identity 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            principal: str，调用方传入的 principal 参数。

        Returns:
            tuple[list[str], list]，函数执行后的结果。
        """
        roles: list[str] = []
        permissions: set = set()
        assignments = await self._rbac_repository.assignments_for_user(tenant_id, principal)
        for assignment in assignments:
            role = await self._rbac_repository.get_role(tenant_id, assignment.role_id)
            if role is not None:
                roles.append(role.name or assignment.role_id)
                permissions |= set(role.permissions)
        return roles, list(permissions)

    async def _record_audit(
        self,
        tenant_id: str,
        decision: AuthorizationDecision,
        ticket: Ticket | None,
    ) -> None:
        """执行 _record_audit 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            decision: AuthorizationDecision，调用方传入的 decision 参数。
            ticket: Ticket | None，调用方传入的 ticket 参数。

        Returns:
            None，函数执行后的结果。
        """
        if self._audit_repository is None:
            return
        risk = (
            ticket.risk_level
            if ticket is not None and ticket.risk_level is not None
            else RiskLevel.HIGH
        )
        await self._audit_repository.save(
            AuditEvent(
                event_id=str(uuid4()),
                tenant_id=tenant_id,
                action=f"{decision.action}.authorization",
                resource_type=decision.resource_type,
                resource_id=decision.resource_id,
                risk_level=RiskLevel.HIGH,
                actor_type="user",
                actor_id=decision.principal,
                payload={
                    "outcome": decision.outcome.value,
                    "reasons": decision.reasons,
                    "approval_ref": decision.approval_ref,
                    "risk_level": risk.value,
                    "authorization_id": decision.authorization_id,
                },
            )
        )

    async def execute_guarded(
        self,
        *,
        tenant_id: str,
        principal: str,
        action: str,
        resource_type: str,
        resource_id: str,
        ticket: Ticket | None,
        fn: Any,
        **kwargs: Any,
    ) -> Any:
        """执行 execute_guarded 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            principal: str，调用方传入的 principal 参数。
            action: str，调用方传入的 action 参数。
            resource_type: str，调用方传入的 resource_type 参数。
            resource_id: str，调用方传入的 resource_id 参数。
            ticket: Ticket | None，调用方传入的 ticket 参数。
            fn: Any，调用方传入的 fn 参数。
            **kwargs: Any，调用方传入的 **kwargs 参数。

        Returns:
            Any，函数执行后的结果。

        Raises:
            PermissionError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        decision = await self.authorize(
            tenant_id=tenant_id,
            principal=principal,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ticket=ticket,
        )
        if decision.outcome != AuthorizationOutcome.ALLOWED:
            raise PermissionError("; ".join(decision.reasons))
        return await fn(**kwargs)
