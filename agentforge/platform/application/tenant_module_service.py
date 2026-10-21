"""租户模块服务模块。"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.risk import RiskLevel
from agentforge.platform.domain.tenant_account import TenantStatus
from agentforge.platform.domain.tenant_module import TenantModuleConfig
from agentforge.platform.sdk.module import ModuleManifest
from agentforge.platform.sdk.ports import AuditPort, OutboxPort

_SENSITIVE_KEY_MARKERS = (
    "secret",
    "password",
    "token",
    "api_key",
    "private_key",
    "credential",
)


class TenantModuleConfigError(ValueError):
    """租户模块错误领域组件。"""


class TenantModuleConfigConflict(TenantModuleConfigError):
    """租户模块冲突相关组件。"""


class TenantModuleRepository(Protocol):
    """租户模块仓储，负责持久化读写。"""

    async def get(self, tenant_id: str, module_name: str) -> TenantModuleConfig | None:
        """读取租户模块。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            module_name: 模块名称。

        Returns:
            租户模块配置无结果。
        """
        ...

    async def list(self, tenant_id: str) -> list[TenantModuleConfig]:
        """查询租户模块。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        ...

    async def save(self, config: TenantModuleConfig) -> None:
        """保存租户模块。

        Args:
            config: 组件配置。
        """
        ...


@dataclass(frozen=True)
class ModuleConfigDefinition:
    """模块定义领域组件。

    Attributes:
        module_name: 模块名称。
        config_schema: 配置结构。
        deployment_defaults: 默认项。
        enabled_by_default: 启用由默认。
    """

    module_name: str
    config_schema: type[BaseModel] | None
    deployment_defaults: Mapping[str, Any]
    enabled_by_default: bool

    def validate(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """校验模块定义。

        Args:
            values: 字段值集合。

        Returns:
            结构化结果字典。

        Raises:
            TenantModuleConfigError: 操作无法完成时抛出。
        """
        if self.config_schema is None:
            return deepcopy(dict(values))
        try:
            model = self.config_schema.model_validate(dict(values))
        except ValidationError as exc:
            raise TenantModuleConfigError(str(exc)) from exc
        return model.model_dump(mode="json")


class TenantModuleConfigAccessor:
    """租户模块相关组件。"""

    def __init__(self, service: "TenantModuleService", module_name: str) -> None:
        """初始化 TenantModuleConfigAccessor。

        Args:
            service: 服务。
            module_name: 模块名称。
        """
        self._service = service
        self._module_name = module_name

    async def effective_values(self, tenant_id: str) -> Mapping[str, Any]:
        """处理值。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        config = await self._service.effective_config(tenant_id, self._module_name)
        return deepcopy(config.values)


class TenantModuleService:
    """租户模块应用服务，编排领域用例及其副作用。"""

    def __init__(
        self,
        repository: TenantModuleRepository,
        audit: AuditPort | None = None,
        outbox: OutboxPort | None = None,
        account_repository=None,
    ) -> None:
        """初始化 TenantModuleService。

        Args:
            repository: 数据仓储实现。
            audit: 审计。
            outbox: Outbox。
            account_repository: 仓储。
        """
        self._repository = repository
        self._audit = audit
        self._outbox = outbox
        self._account_repository = account_repository
        self._definitions: dict[str, ModuleConfigDefinition] = {}

    def register_module(
        self,
        manifest: ModuleManifest,
        deployment_defaults: Mapping[str, Any] | None = None,
    ) -> None:
        """注册模块。

        Args:
            manifest: 模块或资源清单。
            deployment_defaults: 默认项。
        """
        defaults = deepcopy(dict(manifest.config_defaults))
        defaults.update(deepcopy(dict(deployment_defaults or {})))
        definition = ModuleConfigDefinition(
            module_name=manifest.name,
            config_schema=manifest.config_schema,
            deployment_defaults=defaults,
            enabled_by_default=manifest.enabled_by_default,
        )
        # 在启动阶段校验部署配置，
        # 避免租户观察到只完成部分注册的模块。
        definition.validate(defaults)
        self._definitions[manifest.name] = definition

    def list_registered_modules(self) -> tuple[str, ...]:
        """查询已注册模块。

        Returns:
            结果元组。
        """
        return tuple(self._definitions)

    async def is_enabled(self, tenant_id: str, module_name: str) -> bool:
        """判断启用是否成立。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            module_name: 模块名称。

        Returns:
            操作是否成功。
        """
        definition = self._definition(module_name)
        if self._account_repository is not None:
            account = await self._account_repository.get(tenant_id)
            if account is not None and account.status != TenantStatus.ACTIVE:
                return False
        state = await self._repository.get(tenant_id, module_name)
        return definition.enabled_by_default if state is None else state.enabled

    async def list_states(self, tenant_id: str) -> list[TenantModuleConfig]:
        """查询状态。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        return await self._repository.list(tenant_id)

    async def effective_config(
        self,
        tenant_id: str,
        module_name: str,
    ) -> TenantModuleConfig:
        """计算有效配置。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            module_name: 模块名称。

        Returns:
            租户模块配置结果。
        """
        self._require_identity(tenant_id, module_name)
        definition = self._definition(module_name)
        state = await self._repository.get(tenant_id, module_name)
        merged = deepcopy(dict(definition.deployment_defaults))
        if state is not None:
            merged.update(deepcopy(state.values))
        validated = definition.validate(merged)
        return TenantModuleConfig(
            tenant_id=tenant_id,
            module_name=module_name,
            enabled=definition.enabled_by_default if state is None else state.enabled,
            config_version=1 if state is None else state.config_version,
            source="deployment_default" if state is None else "tenant_override",
            updated_by="" if state is None else state.updated_by,
            plan_name="" if state is None else state.plan_name,
            updated_at=None if state is None else state.updated_at,
            values=validated,
            secret_refs={} if state is None else deepcopy(state.secret_refs),
        )

    async def describe_module(self, tenant_id: str, module_name: str) -> dict[str, Any]:
        """描述模块。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            module_name: 模块名称。

        Returns:
            结构化结果字典。
        """
        definition = self._definition(module_name)
        effective = await self.effective_config(tenant_id, module_name)
        state = await self._repository.get(tenant_id, module_name)
        return {
            "module_name": module_name,
            "enabled": effective.enabled,
            "source": effective.source,
            "config_version": effective.config_version,
            "updated_by": effective.updated_by,
            "plan_name": effective.plan_name,
            "updated_at": (
                effective.updated_at.isoformat() if effective.updated_at is not None else None
            ),
            "values": effective.values,
            "secret_refs": effective.secret_refs,
            "deployment_defaults": deepcopy(dict(definition.deployment_defaults)),
            "config_schema": (
                definition.config_schema.model_json_schema()
                if definition.config_schema is not None
                else None
            ),
            "has_tenant_override": state is not None,
        }

    async def describe_modules(self, tenant_id: str) -> list[dict[str, Any]]:
        """描述模块。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        return [
            await self.describe_module(tenant_id, module_name) for module_name in self._definitions
        ]

    async def set_enabled(
        self,
        *,
        tenant_id: str,
        module_name: str,
        enabled: bool,
        actor_id: str,
        plan_name: str = "",
    ) -> TenantModuleConfig:
        """设置启用。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            module_name: 模块名称。
            enabled: 启用。
            actor_id: 执行操作的参与者 ID。
            plan_name: 套餐名称。

        Returns:
            租户模块配置结果。
        """
        self._require_actor(actor_id)
        definition = self._definition(module_name)
        previous = await self._repository.get(tenant_id, module_name)
        now = datetime.now(timezone.utc)
        state = TenantModuleConfig(
            tenant_id=tenant_id,
            module_name=module_name,
            enabled=enabled,
            config_version=1 if previous is None else previous.config_version,
            source="tenant_override",
            updated_by=actor_id.strip(),
            plan_name=plan_name,
            updated_at=now,
            values={} if previous is None else deepcopy(previous.values),
            secret_refs={} if previous is None else deepcopy(previous.secret_refs),
        )
        # 保持最强约束：即使只变更启用状态，
        # 最终生效配置也必须始终有效。
        await self.effective_config_after_override(state, definition)
        await self._repository.save(state)
        action = f"tenant.module.{'enabled' if enabled else 'disabled'}"
        await self._record_change(
            action=action,
            state=state,
            payload={
                "enabled": enabled,
                "previous_enabled": (
                    definition.enabled_by_default if previous is None else previous.enabled
                ),
                "plan_name": plan_name,
                "config_version": state.config_version,
            },
            event_type="platform.tenant_module.enabled_changed.v1",
        )
        return state

    async def set_config(
        self,
        *,
        tenant_id: str,
        module_name: str,
        values: Mapping[str, Any],
        actor_id: str,
        secret_refs: Mapping[str, str] | None = None,
        expected_version: int | None = None,
        enabled: bool | None = None,
    ) -> TenantModuleConfig:
        """设置并持久化租户模块配置。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            module_name: 模块名称。
            values: 字段值集合。
            actor_id: 执行操作的参与者 ID。
            secret_refs: 密钥。
            expected_version: 版本。
            enabled: 启用。

        Returns:
            租户模块配置结果。

        Raises:
            TenantModuleConfigConflict: 操作无法完成时抛出。
        """
        self._require_actor(actor_id)
        self._require_identity(tenant_id, module_name)
        definition = self._definition(module_name)
        self._reject_plaintext_secrets(values)
        previous = await self._repository.get(tenant_id, module_name)
        current_version = 1 if previous is None else previous.config_version
        if expected_version is not None and expected_version != current_version:
            raise TenantModuleConfigConflict(
                f"config version conflict: expected {expected_version}, current {current_version}"
            )
        merged = deepcopy(dict(definition.deployment_defaults))
        merged.update(deepcopy(dict(values)))
        definition.validate(merged)
        now = datetime.now(timezone.utc)
        state = TenantModuleConfig(
            tenant_id=tenant_id,
            module_name=module_name,
            enabled=(
                definition.enabled_by_default
                if previous is None and enabled is None
                else previous.enabled if previous is not None and enabled is None else bool(enabled)
            ),
            config_version=current_version + 1,
            source="tenant_override",
            updated_by=actor_id.strip(),
            updated_at=now,
            values=deepcopy(dict(values)),
            secret_refs=deepcopy(dict(secret_refs or {})),
        )
        await self._repository.save(state)
        previous_values = (
            deepcopy(dict(definition.deployment_defaults))
            if previous is None
            else deepcopy(dict(previous.values))
        )
        changed_keys = sorted(
            key
            for key in set(previous_values) | set(state.values)
            if previous_values.get(key) != state.values.get(key)
        )
        await self._record_change(
            action="tenant.module.config_updated",
            state=state,
            payload={
                "config_version": state.config_version,
                "previous_config_version": current_version,
                "changed_keys": changed_keys,
                "source": state.source,
                "secret_reference_keys": sorted(state.secret_refs),
            },
            event_type="platform.tenant_module.config_changed.v1",
        )
        return state

    async def effective_config_after_override(
        self,
        state: TenantModuleConfig,
        definition: ModuleConfigDefinition,
    ) -> dict[str, Any]:
        """处理配置之后覆盖。

        Args:
            state: 当前状态。
            definition: 输入参数。

        Returns:
            结构化结果字典。
        """
        merged = deepcopy(dict(definition.deployment_defaults))
        merged.update(deepcopy(state.values))
        return definition.validate(merged)

    def _definition(self, module_name: str) -> ModuleConfigDefinition:
        """执行定义。

        Args:
            module_name: 模块名称。

        Returns:
            模块配置结果。

        Raises:
            TenantModuleConfigError: 操作无法完成时抛出。
        """
        definition = self._definitions.get(module_name)
        if definition is None:
            raise TenantModuleConfigError(f"module is not deployed: {module_name}")
        return definition

    @staticmethod
    def _require_identity(tenant_id: str, module_name: str) -> None:
        """执行校验身份。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            module_name: 模块名称。

        Raises:
            TenantModuleConfigError: 操作无法完成时抛出。
        """
        if not tenant_id.strip() or not module_name.strip():
            raise TenantModuleConfigError("tenant_id and module_name are required")

    @staticmethod
    def _require_actor(actor_id: str) -> None:
        """处理要求。

        Args:
            actor_id: 执行操作的参与者 ID。

        Raises:
            TenantModuleConfigError: 操作无法完成时抛出。
        """
        if not actor_id.strip():
            raise TenantModuleConfigError("actor_id is required")

    @staticmethod
    def _reject_plaintext_secrets(values: Mapping[str, Any]) -> None:
        """拒绝明文密钥。

        Args:
            values: 字段值集合。
        """

        def walk(value: Any, path: str) -> None:
            """遍历租户模块。

            Args:
                value: 待处理值。
                path: 文件或资源路径。

            Raises:
                TenantModuleConfigError: 操作无法完成时抛出。
            """
            if isinstance(value, Mapping):
                for raw_key, child in value.items():
                    key = str(raw_key)
                    lowered = key.lower()
                    if any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS):
                        raise TenantModuleConfigError(
                            f"sensitive field {path}{key} must be supplied via secret_refs"
                        )
                    walk(child, f"{path}{key}.")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    walk(child, f"{path}{index}.")

        walk(values, "")

    async def _record_change(
        self,
        *,
        action: str,
        state: TenantModuleConfig,
        payload: dict[str, Any],
        event_type: str,
    ) -> None:
        """记录租户模块。

        Args:
            action: 待执行动作名称。
            state: 当前状态。
            payload: 事件、工作流或请求载荷。
            event_type: 事件类型。
        """
        trace_id = str(uuid4())
        if self._audit is not None:
            await self._audit.save(
                AuditEvent(
                    event_id=str(uuid4()),
                    tenant_id=state.tenant_id,
                    action=action,
                    resource_type="tenant_module",
                    resource_id=state.module_name,
                    risk_level=RiskLevel.HIGH,
                    actor_type="user",
                    actor_id=state.updated_by,
                    trace_id=trace_id,
                    payload=payload,
                )
            )
        if self._outbox is not None:
            await self._outbox.enqueue(
                EventEnvelope(
                    event_id=str(uuid4()),
                    event_type=event_type,
                    event_version=1,
                    tenant_id=state.tenant_id,
                    task_id=state.module_name,
                    trace_id=trace_id,
                    producer="tenant-module-service",
                    payload={
                        "module_name": state.module_name,
                        "enabled": state.enabled,
                        "config_version": state.config_version,
                        **payload,
                    },
                )
            )


__all__ = [
    "ModuleConfigDefinition",
    "TenantModuleConfigAccessor",
    "TenantModuleConfigConflict",
    "TenantModuleConfigError",
    "TenantModuleRepository",
    "TenantModuleService",
]
