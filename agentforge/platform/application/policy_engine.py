from __future__ import annotations

from collections.abc import Iterable

from agentforge.platform.domain.policy import (
    ActionPolicy,
    PolicyDecision,
    ValidationOutcome,
)
from agentforge.platform.domain.rbac import Permission, role_permissions


class PolicyEngine:
    """Deterministic RBAC + policy evaluation engine.

    Combines role-based permissions with declarative action policies and an
    optional OpenFGA-style relation check (via a callable) to decide whether a
    principal may run ``action`` on ``resource``. Fails closed: an action with
    no matching enabled policy is denied. High-risk write actions that require
    approval yield ``requires_approval`` instead of an immediate allow.
    """

    def __init__(
        self,
        policies: Iterable[ActionPolicy] | None = None,
        relation_check=None,
    ) -> None:
        self._policies: dict[tuple[str, str], ActionPolicy] = {}
        for policy in policies or ():
            self._store(policy)
        # relation_check: async callable (RelationTuple) -> bool
        self._relation_check = relation_check

    def _store(self, policy: ActionPolicy) -> None:
        key = (policy.tenant_id, policy.action)
        self._policies[key] = policy

    def register_policy(self, policy: ActionPolicy) -> None:
        self._store(policy)

    def list_policies(self, tenant_id: str) -> list[ActionPolicy]:
        return [policy for (t, _a), policy in self._policies.items() if t == tenant_id]

    async def authorize(
        self,
        *,
        tenant_id: str,
        principal: str,
        action: str,
        roles: Iterable[str],
        permissions: Iterable[Permission] | None = None,
        resource_type: str = "",
        resource_id: str = "",
        relation: str | None = None,
    ) -> PolicyDecision:
        roles = set(roles)
        perms = set(permissions or [])
        for role in roles:
            perms |= role_permissions(role)

        policy = self._policies.get((tenant_id, action))
        if policy is None:
            policy = self._policies.get(("*", action))
        if policy is None:
            return PolicyDecision(
                tenant_id=tenant_id,
                principal=principal,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=ValidationOutcome.DENIED,
                risk_level="low",
                reasons=["no policy registered for action"],
            )
        if not policy.enabled:
            return PolicyDecision(
                tenant_id=tenant_id,
                principal=principal,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=ValidationOutcome.DENIED,
                risk_level=policy.risk_level,
                reasons=["policy disabled"],
            )

        # Optional OpenFGA-style relation check gates access to the resource.
        if relation is not None and self._relation_check is not None:
            allowed_relation = await self._check_relation(
                tenant_id, resource_type, resource_id, relation, principal
            )
            if not allowed_relation:
                return PolicyDecision(
                    tenant_id=tenant_id,
                    principal=principal,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    outcome=ValidationOutcome.DENIED,
                    risk_level=policy.risk_level,
                    reasons=[f"relation {relation} not granted"],
                )

        # High-risk write actions require an approval step after the role /
        # permission gate passes (permission is checked first so an
        # unauthorized principal cannot sneak through just because a ticket was
        # approved).

        # Role / permission check.
        if policy.required_permission:
            try:
                needed = Permission(policy.required_permission)
            except ValueError:
                needed = None
            if needed is not None:
                if needed not in perms:
                    return PolicyDecision(
                        tenant_id=tenant_id,
                        principal=principal,
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        outcome=ValidationOutcome.DENIED,
                        risk_level=policy.risk_level,
                        reasons=[f"missing permission {policy.required_permission}"],
                    )

        allowed_roles = set(policy.allowed_roles)
        if allowed_roles and not (roles & allowed_roles):
            return PolicyDecision(
                tenant_id=tenant_id,
                principal=principal,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=ValidationOutcome.DENIED,
                risk_level=policy.risk_level,
                reasons=["role not allow-listed"],
            )

        # Permission / role gate passed; now apply the approval requirement.
        if policy.require_approval:
            return PolicyDecision(
                tenant_id=tenant_id,
                principal=principal,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=ValidationOutcome.REQUIRES_APPROVAL,
                risk_level=policy.risk_level,
                reasons=["action requires approval"],
            )

        # Allow.
        if policy.required_permission:
            try:
                needed = Permission(policy.required_permission)
            except ValueError:
                needed = None
            if needed is not None:
                return PolicyDecision(
                    tenant_id=tenant_id,
                    principal=principal,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    outcome=ValidationOutcome.ALLOWED,
                    risk_level=policy.risk_level,
                    reasons=["permission granted"],
                )

        if not allowed_roles or roles & allowed_roles:
            return PolicyDecision(
                tenant_id=tenant_id,
                principal=principal,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome=ValidationOutcome.ALLOWED,
                risk_level=policy.risk_level,
                reasons=(["role allow-listed"] if allowed_roles else ["open policy"]),
            )
        return PolicyDecision(
            tenant_id=tenant_id,
            principal=principal,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=ValidationOutcome.DENIED,
            risk_level=policy.risk_level,
            reasons=["role not allow-listed"],
        )

    async def _check_relation(
        self,
        tenant_id: str,
        resource_type: str,
        resource_id: str,
        relation: str,
        principal: str,
    ) -> bool:
        from agentforge.platform.domain.policy import RelationTuple

        result = await self._relation_check(
            RelationTuple(
                tenant_id=tenant_id,
                object_type=resource_type,
                object_id=resource_id,
                relation=relation,
                subject_type="user",
                subject_id=principal,
            )
        )
        return bool(result)
