"""授权服务模块。"""

from __future__ import annotations

from uuid import uuid4

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.authorization import AuthorizationDecision, AuthorizationOutcome
from agentforge.platform.domain.risk import RiskLevel
from agentforge.platform.sdk.ports import AuditPort, PolicyPort, RbacPort


class AuthorizationService:
    """授权应用服务，编排领域用例及其副作用。"""

    def __init__(
        self,
        policy: PolicyPort,
        rbac: RbacPort,
        audit: AuditPort | None = None,
    ) -> None:
        """初始化 AuthorizationService。

        Args:
            policy: 策略定义。
            rbac: RBAC。
            audit: 审计。
        """
        self._policy = policy
        self._rbac = rbac
        self._audit = audit

    async def authorize(
        self,
        *,
        tenant_id: str,
        principal: str,
        action: str,
        resource_type: str,
        resource_id: str,
        relation: str | None = None,
    ) -> AuthorizationDecision:
        """执行授权决策。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            principal: 当前认证主体。
            action: 待执行动作名称。
            resource_type: 资源类型。
            resource_id: 资源 ID。
            relation: 关系。

        Returns:
            决策结果。
        """
        roles, permissions = await self._resolve_identity(tenant_id, principal)
        policy_decision = await self._policy.authorize(
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
        outcome = outcome_map.get(
            policy_decision.outcome.value,
            AuthorizationOutcome.DENIED,
        )
        decision = AuthorizationDecision(
            authorization_id=f"authz-{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            principal=principal,
            outcome=outcome,
            reasons=list(policy_decision.reasons),
        )
        await self._record(decision, policy_decision.risk_level)
        return decision

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
        assignments = await self._rbac.assignments_for_user(tenant_id, principal)
        for assignment in assignments:
            role = await self._rbac.get_role(tenant_id, assignment.role_id)
            if role is not None:
                roles.add(role.name or assignment.role_id)
                permissions |= set(role.permissions)
        return roles, permissions

    async def _record(self, decision: AuthorizationDecision, risk_level: str) -> None:
        """记录授权。

        Args:
            decision: 待处理的授权或审批决策。
            risk_level: 风险级别。
        """
        if self._audit is None:
            return
        try:
            risk = RiskLevel(risk_level)
        except ValueError:
            risk = RiskLevel.HIGH
        await self._audit.save(
            AuditEvent(
                event_id=str(uuid4()),
                tenant_id=decision.tenant_id,
                action=f"{decision.action}.authorization",
                resource_type=decision.resource_type,
                resource_id=decision.resource_id,
                risk_level=risk,
                actor_type="user",
                actor_id=decision.principal,
                payload={
                    "outcome": decision.outcome.value,
                    "reasons": decision.reasons,
                    "authorization_id": decision.authorization_id,
                },
            )
        )
