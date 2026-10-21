"""策略引擎模块。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from agentforge.platform.domain.policy import ActionPolicy, PolicyDecision, ValidationOutcome
from agentforge.platform.domain.rbac import role_permissions


@dataclass(frozen=True)
class PolicyReloadEvent:
    """策略重新加载事件相关组件。

    Attributes:
        revision: 修订。
        policy_count: 策略数量。
        source: 调用或事件来源。
        occurred_at: 用量发生时间。
    """

    revision: int
    policy_count: int
    source: str
    occurred_at: datetime


class PolicyEngine:
    """策略领域组件。"""

    def __init__(
        self,
        policies: Iterable[ActionPolicy] | None = None,
        relation_check=None,
        reload_listener: Callable[[PolicyReloadEvent], object] | None = None,
    ) -> None:
        """初始化 PolicyEngine。

        Args:
            policies: 策略。
            relation_check: 关系检查。
            reload_listener: 重新加载。
        """
        self._policies: dict[tuple[str, str], ActionPolicy] = {}
        for policy in policies or ():
            self._store(policy)
        self._relation_check = relation_check
        self._source_revision = 0
        # 验证成功场景，确保正常路径行为稳定。
        # 验证审计记录，确保关键行为可追踪。
        self._reload_listener = reload_listener

    @staticmethod
    def _validate_policy(policy: ActionPolicy) -> None:
        """校验策略。

        Args:
            policy: 策略定义。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if policy.required_permission is None:
            return
        if not policy.required_permission.strip():
            raise ValueError(
                f"invalid required_permission {policy.required_permission!r} "
                f"for policy {policy.name!r}"
            )

    def _store(self, policy: ActionPolicy) -> None:
        """保存当前记录。

        Args:
            policy: 策略定义。
        """
        self._validate_policy(policy)
        key = (policy.tenant_id, policy.action)
        self._policies[key] = policy

    def register_policy(self, policy: ActionPolicy) -> None:
        """注册策略。

        Args:
            policy: 策略定义。
        """
        self._store(policy)

    def list_policies(self, tenant_id: str) -> list[ActionPolicy]:
        """查询策略。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        return [policy for (t, _a), policy in self._policies.items() if t == tenant_id]

    @property
    def source_revision(self) -> int:
        """返回来源修订。

        Returns:
            整数结果。
        """
        return self._source_revision

    def reload(self, policies: Iterable[ActionPolicy]) -> int:
        """重新加载策略。

        Args:
            policies: 策略。

        Returns:
            整数结果。
        """
        rev = self._swap(policies)
        self._emit_reload_event("reload")
        return rev

    def reload_from_loader(self, loader) -> int:
        """重新加载从加载器。

        Args:
            loader: 加载器。

        Returns:
            整数结果。
        """
        loaded = loader()
        rev = self._swap(loaded)
        self._emit_reload_event("reload_from_loader")
        return rev

    def _swap(self, policies: Iterable[ActionPolicy]) -> int:
        """交换策略。

        Args:
            policies: 策略。

        Returns:
            整数结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
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
        permissions: Iterable[str] | None = None,
        resource_type: str = "",
        resource_id: str = "",
        relation: str | None = None,
    ) -> PolicyDecision:
        """授权策略。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            principal: 当前认证主体。
            action: 待执行动作名称。
            roles: 角色。
            permissions: 权限。
            resource_type: 资源类型。
            resource_id: 资源 ID。
            relation: 关系。

        Returns:
            策略决策结果。
        """
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

        # 验证审批边界，确保高风险动作必须经过审批。
        if policy.required_permission:
            needed = policy.required_permission
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

        # 验证审批边界，确保高风险动作必须经过审批。
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
        """发送重新加载事件。

        Args:
            source: 调用或事件来源。
        """
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
        """检查关系。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            resource_type: 资源类型。
            resource_id: 资源 ID。
            relation: 关系。
            principal: 当前认证主体。

        Returns:
            操作是否成功。
        """
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
