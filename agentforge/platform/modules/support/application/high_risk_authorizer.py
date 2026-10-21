"""高风险授权器模块。"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.authorization import AuthorizationDecision, AuthorizationOutcome
from agentforge.platform.modules.support.domain.ticket import RiskLevel, Ticket, TicketStatus
from agentforge.platform.sdk.ports import AuditPort, PolicyPort, RbacPort


class HighRiskActionAuthorizer:
    """高风险操作授权器相关组件。"""

    def __init__(
        self,
        policy_engine: PolicyPort,
        audit_repository: AuditPort | None = None,
        rbac_repository: RbacPort | None = None,
    ) -> None:
        """初始化 HighRiskActionAuthorizer。

        Args:
            policy_engine: 策略引擎。
            audit_repository: 审计仓储。
            rbac_repository: RBAC仓储。
        """
        self._policy_engine = policy_engine
        self._audit_repository = audit_repository
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
        """执行授权决策。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            principal: 当前认证主体。
            action: 待执行动作名称。
            resource_type: 资源类型。
            resource_id: 资源 ID。
            ticket: 客服工单对象。
            relation: 关系。
            record: 待处理的领域记录。

        Returns:
            决策结果。
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
        """处理审批。

        Args:
            ticket: 客服工单对象。

        Returns:
            无结果。
        """
        if ticket is None:
            return None
        if ticket.status != TicketStatus.READY_TO_PUBLISH:
            return None
        approval = ticket.metadata.get("approval") or {}
        if approval.get("decision") != "approve":
            return None
        return approval.get("decided_by") or ticket.ticket_id

    async def _resolve_identity(self, tenant_id: str, principal: str) -> tuple[set[str], set[str]]:
        """解析身份。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            principal: 当前认证主体。

        Returns:
            结果元组。
        """
        roles: set[str] = set()
        permissions: set[str] = set()
        assignments = await self._rbac_repository.assignments_for_user(tenant_id, principal)
        for assignment in assignments:
            role = await self._rbac_repository.get_role(tenant_id, assignment.role_id)
            if role is not None:
                roles.add(role.name or assignment.role_id)
                permissions |= set(role.permissions)
        return roles, permissions

    async def _record_audit(
        self,
        tenant_id: str,
        decision: AuthorizationDecision,
        ticket: Ticket | None,
    ) -> None:
        """记录审计。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            decision: 待处理的授权或审批决策。
            ticket: 客服工单对象。
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
        """执行带审批和策略校验的高风险动作。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            principal: 当前认证主体。
            action: 待执行动作名称。
            resource_type: 资源类型。
            resource_id: 资源 ID。
            ticket: 客服工单对象。
            fn: 函数。
            kwargs: 关键字参数。

        Returns:
            处理结果对象。

        Raises:
            PermissionError: 调用方缺少所需权限时抛出。
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
