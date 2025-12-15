from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from agentforge.platform.domain.policy import (
    ActionPolicy,
    PolicyDecision,
    ValidationOutcome,
)
from agentforge.platform.domain.rbac import Permission, role_permissions


@dataclass(frozen=True)
class PolicyReloadEvent:
    """Versioned audit record emitted after a successful policy reload.

    A reload bumps ``source_revision`` monotonically; this event carries the
    new revision plus a fingerprint of what changed so the host application
    can persist a durable, version-stamped audit trail (e.g. as an
    ``AuditEvent``). Only emitted via the optional ``reload_listener`` hook --
    the engine itself stays free of I/O concerns.
    """

    revision: int
    policy_count: int
    source: str
    occurred_at: datetime


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
        reload_listener: Callable[[PolicyReloadEvent], object] | None = None,
    ) -> None:
        self._policies: dict[tuple[str, str], ActionPolicy] = {}
        for policy in policies or ():
            self._store(policy)
        # relation_check: async callable (RelationTuple) -> bool
        self._relation_check = relation_check
        # monotonic revision bumped on every (re)load, so callers can detect
        # a hot-reload and trace which policy set a decision was made against.
        self._source_revision = 0
        # Optional hook: after a successful atomic reload, emit a versioned
        # PolicyReloadEvent so the host can write a durable audit trail.
        self._reload_listener = reload_listener

    @staticmethod
    def _validate_policy(policy: ActionPolicy) -> None:
        """Fail closed on a misconfigured policy.

        ``required_permission`` must be a valid :class:`Permission` value or the
        policy is rejected outright. An unrecognised string must never be
        silently downgraded (e.g. to ``None``) at authorize time, which would let
        a typo'd config degrade an action into an open policy and contradict the
        engine's fail-closed contract.
        """
        if policy.required_permission is None:
            return
        try:
            Permission(policy.required_permission)
        except ValueError as exc:
            raise ValueError(
                f"invalid required_permission {policy.required_permission!r} "
                f"for policy {policy.name!r}"
            ) from exc

    def _store(self, policy: ActionPolicy) -> None:
        self._validate_policy(policy)
        key = (policy.tenant_id, policy.action)
        self._policies[key] = policy

    def register_policy(self, policy: ActionPolicy) -> None:
        self._store(policy)

    def list_policies(self, tenant_id: str) -> list[ActionPolicy]:
        return [policy for (t, _a), policy in self._policies.items() if t == tenant_id]

    @property
    def source_revision(self) -> int:
        """Monotonic revision of the currently loaded policy set."""
        return self._source_revision

    def reload(self, policies: Iterable[ActionPolicy]) -> int:
        """Atomically replace all policies with ``policies``.

        Validation/construction of the new set is the caller's responsibility
        (e.g. via :class:`PolicyFileLoader`); here we build the new registry
        fully before swapping, so a bad replacement never leaves a partially
        updated engine. Emits a :class:`PolicyReloadEvent` on success. Returns
        the new ``source_revision``.
        """
        rev = self._swap(policies)
        self._emit_reload_event("reload")
        return rev

    def reload_from_loader(self, loader) -> int:
        """Hot-reload from a loader/producer yielding ``ActionPolicy`` s.

        The loader is invoked first and must succeed entirely; only then is
        the engine registry swapped (atomic). On loader failure the engine is
        left untouched and the previous policy set stays authoritative. Emits
        a :class:`PolicyReloadEvent` on success.
        """
        loaded = loader()
        rev = self._swap(loaded)
        self._emit_reload_event("reload_from_loader")
        return rev

    def _swap(self, policies: Iterable[ActionPolicy]) -> int:
        """Build and atomically install a new policy registry.

        Constructs the replacement dict in full and validates against duplicate
        keys before swapping ``self._policies``; increments ``source_revision``
        afterwards. Raises ``ValueError`` on a duplicate key or an invalid
        ``required_permission`` and leaves the engine unchanged.
        """
        new_registry: dict[tuple[str, str], ActionPolicy] = {}
        for policy in policies:
            key = (policy.tenant_id, policy.action)
            if key in new_registry:
                raise ValueError(f"duplicate policy key {key!r} while reloading")
            self._validate_policy(policy)
            new_registry[key] = policy
        self._policies = new_registry
        self._source_revision += 1
        return self._source_revision

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

        # Permission check. ``required_permission`` is validated to be a real
        # :class:`Permission` at load/register time (fail-closed), so a typo'd
        # value can never silently degrade to ``None`` and become an open
        # policy. This check runs before the approval gate so an unauthorized
        # principal cannot sneak through just because a ticket was approved.
        if policy.required_permission:
            needed = Permission(policy.required_permission)
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

        # Allow: a permission-backed policy already passed its permission check
        # above; an allow-list-restricted (or open but permission-gated) policy
        # is permitted when the caller's roles intersect the allow-list.
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

    def _emit_reload_event(self, source: str) -> None:
        if self._reload_listener is None:
            return
        event = PolicyReloadEvent(
            revision=self._source_revision,
            policy_count=len(self._policies),
            source=source,
            occurred_at=datetime.now(timezone.utc),
        )
        self._reload_listener(event)

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
