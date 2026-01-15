"""AgentForge 平台应用服务层：policy_engine。

本模块负责 policy_engine 相关的平台能力，是 平台应用服务层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：PolicyReloadEvent、PolicyEngine。
"""

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
    """PolicyReloadEvent。

    PolicyReloadEvent 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - revision: int。
    - policy_count: int。
    - source: str。
    - occurred_at: datetime。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    revision: int
    policy_count: int
    source: str
    occurred_at: datetime


class PolicyEngine:
    """PolicyEngine。

    PolicyEngine 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 register_policy()。
    - 方法 list_policies()。
    - 方法 source_revision()。
    - 方法 reload()。
    - 方法 reload_from_loader()。
    - 方法 authorize()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        policies: Iterable[ActionPolicy] | None = None,
        relation_check=None,
        reload_listener: Callable[[PolicyReloadEvent], object] | None = None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            policies: Iterable[ActionPolicy] | None，调用方传入的 policies 参数。
            relation_check: Any，调用方传入的 relation_check 参数。
            reload_listener: Callable[[PolicyReloadEvent], object] | None，调用方传入的 reload_listener 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._policies: dict[tuple[str, str], ActionPolicy] = {}
        for policy in policies or ():
            self._store(policy)
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        self._relation_check = relation_check
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        self._source_revision = 0
        # 验证成功场景，确保正常路径行为稳定。
        # 验证审计记录，确保关键行为可追踪。
        self._reload_listener = reload_listener

    @staticmethod
    def _validate_policy(policy: ActionPolicy) -> None:
        """执行 _validate_policy 对应的逻辑，并返回处理结果。

        Args:
            policy: ActionPolicy，调用方传入的 policy 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
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
        """执行 _store 对应的逻辑，并返回处理结果。

        Args:
            policy: ActionPolicy，调用方传入的 policy 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._validate_policy(policy)
        key = (policy.tenant_id, policy.action)
        self._policies[key] = policy

    def register_policy(self, policy: ActionPolicy) -> None:
        """执行 register_policy 对应的逻辑，并返回处理结果。

        Args:
            policy: ActionPolicy，调用方传入的 policy 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._store(policy)

    def list_policies(self, tenant_id: str) -> list[ActionPolicy]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            list[ActionPolicy]，函数执行后的结果。
        """
        return [policy for (t, _a), policy in self._policies.items() if t == tenant_id]

    @property
    def source_revision(self) -> int:
        """执行 source_revision 对应的逻辑，并返回处理结果。

        Returns:
            int，函数执行后的结果。
        """
        return self._source_revision

    def reload(self, policies: Iterable[ActionPolicy]) -> int:
        """执行 reload 对应的逻辑，并返回处理结果。

        Args:
            policies: Iterable[ActionPolicy]，调用方传入的 policies 参数。

        Returns:
            int，函数执行后的结果。
        """
        rev = self._swap(policies)
        self._emit_reload_event("reload")
        return rev

    def reload_from_loader(self, loader) -> int:
        """执行 reload_from_loader 对应的逻辑，并返回处理结果。

        Args:
            loader: Any，调用方传入的 loader 参数。

        Returns:
            int，函数执行后的结果。
        """
        loaded = loader()
        rev = self._swap(loaded)
        self._emit_reload_event("reload_from_loader")
        return rev

    def _swap(self, policies: Iterable[ActionPolicy]) -> int:
        """执行 _swap 对应的逻辑，并返回处理结果。

        Args:
            policies: Iterable[ActionPolicy]，调用方传入的 policies 参数。

        Returns:
            int，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
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
        """执行 authorize 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            principal: str，调用方传入的 principal 参数。
            action: str，调用方传入的 action 参数。
            roles: Iterable[str]，调用方传入的 roles 参数。
            permissions: Iterable[Permission] | None，调用方传入的 permissions 参数。
            resource_type: str，调用方传入的 resource_type 参数。
            resource_id: str，调用方传入的 resource_id 参数。
            relation: str | None，调用方传入的 relation 参数。

        Returns:
            PolicyDecision，函数执行后的结果。
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

        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
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

        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        # 验证审批边界，确保高风险动作必须经过审批。
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
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

        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
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
        """执行 _emit_reload_event 对应的逻辑，并返回处理结果。

        Args:
            source: str，调用方传入的 source 参数。

        Returns:
            None，函数执行后的结果。
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
        """执行 _check_relation 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            resource_type: str，调用方传入的 resource_type 参数。
            resource_id: str，调用方传入的 resource_id 参数。
            relation: str，调用方传入的 relation 参数。
            principal: str，调用方传入的 principal 参数。

        Returns:
            bool，函数执行后的结果。
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
