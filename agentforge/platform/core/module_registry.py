"""模块注册表模块。"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, ValidationError

from agentforge.core.base_tool import BaseTool
from agentforge.platform.sdk.connector import ConnectorRegistration
from agentforge.platform.sdk.module import (
    BusinessModule,
    EventHandler,
    MetricProvider,
    ModuleConfig,
    ModuleContext,
    ModuleManifest,
    ModuleRuntime,
)

ModuleContextFactory = Callable[[ModuleManifest], ModuleContext]


DEFAULT_CORE_CAPABILITIES: frozenset[str] = frozenset(
    {
        "core.audit",
        "core.auth",
        "core.config",
        "core.connector",
        "core.cost",
        "core.evaluation",
        "core.identity",
        "core.knowledge",
        "core.model",
        "core.object_store",
        "core.outbox",
        "core.persistence",
        "core.policy",
        "core.tenant",
        "core.workflow",
    }
)

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_API_PREFIX_PATTERN = re.compile(r"^/v1/[a-z0-9]+(?:-[a-z0-9]+)*(?:/[a-z0-9]+(?:-[a-z0-9]+)*)*$")
_TASK_QUEUE_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
_PERMISSION_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*$")
_MIGRATION_NAMESPACE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class ModuleRegistrationError(ValueError):
    """模块注册或契约校验失败。"""


@dataclass(frozen=True)
class RegisteredModule:
    """已通过校验并构建完成的模块。

    Attributes:
        module: 模块。
        manifest: 清单。
        runtime: 运行时。
        validated_config: 已验证配置。
    """

    module: BusinessModule
    manifest: ModuleManifest
    runtime: ModuleRuntime
    validated_config: BaseModel | None = None


class ModuleRegistry:
    """管理业务模块的生命周期与注册冲突。"""

    def __init__(
        self,
        context_factory: ModuleContextFactory,
        *,
        available_core_capabilities: frozenset[str] = DEFAULT_CORE_CAPABILITIES,
        supported_contract_versions: frozenset[int] = frozenset({1}),
        platform_version: str = "3.1.0",
    ) -> None:
        """初始化 ModuleRegistry。

        Args:
            context_factory: 上下文工厂。
            available_core_capabilities: 可用核心。
            supported_contract_versions: 契约。
            platform_version: 平台版本。
        """
        self._context_factory = context_factory
        self._available_core_capabilities = available_core_capabilities
        self._supported_contract_versions = supported_contract_versions
        self._platform_version = self._parse_version(platform_version)
        self._modules: dict[str, RegisteredModule] = {}
        self._api_prefixes: set[str] = set()
        self._task_queues: set[str] = set()
        self._permissions: set[str] = set()
        self._published_events: set[str] = set()
        self._tool_names: set[str] = set()
        self._connector_ids: set[str] = set()
        self._workflow_names: set[str] = set()
        self._route_keys: set[tuple[str, str]] = set()

    def register(self, module: BusinessModule) -> RegisteredModule:
        """校验并注册一个业务模块。

        Args:
            module: 模块。

        Returns:
            已注册模块结果。

        Raises:
            ModuleRegistrationError: 操作无法完成时抛出。
        """
        manifest = module.manifest
        if not isinstance(manifest, ModuleManifest):
            raise ModuleRegistrationError("module.manifest must be ModuleManifest")
        if manifest.name in self._modules:
            raise ModuleRegistrationError(f"module already registered: {manifest.name}")
        self._validate_manifest(manifest)

        context = self._context_factory(manifest)
        context = replace(
            context,
            config=ModuleConfig(
                values={
                    **dict(manifest.config_defaults),
                    **dict(context.config.values),
                }
            ),
        )
        self._validate_context(manifest, context)
        validated_config = self._validate_config(manifest, context)
        runtime = module.build(context)
        if not isinstance(runtime, ModuleRuntime):
            raise ModuleRegistrationError(
                f"module {manifest.name!r} build() must return ModuleRuntime"
            )
        self._validate_runtime(manifest, runtime)
        self._validate_route_conflicts(manifest, runtime)

        registered = RegisteredModule(
            module=module,
            manifest=manifest,
            runtime=runtime,
            validated_config=validated_config,
        )
        self._modules[manifest.name] = registered
        self._api_prefixes.add(manifest.api_prefix)
        self._task_queues.add(manifest.task_queue)
        self._permissions.update(manifest.permissions)
        self._published_events.update(manifest.published_events)
        self._tool_names.update(tool.name for tool in runtime.agent_tools)
        self._connector_ids.update(
            registration.connector_id for registration in runtime.connector_registrations
        )
        self._workflow_names.update(workflow.__name__ for workflow in runtime.temporal_workflows)
        self._claim_route_keys(manifest, runtime)
        return registered

    def validate(self) -> None:
        """对已注册模块做一次完整清单和依赖校验。"""
        for registered in self._modules.values():
            self._validate_manifest(registered.manifest, check_global=False)
            self._validate_runtime(registered.manifest, registered.runtime, check_global=False)

    def get(self, name: str) -> RegisteredModule | None:
        """按名称读取已注册模块。

        Args:
            name: 资源或对象名称。

        Returns:
            已注册模块无结果。
        """
        return self._modules.get(name)

    def list_modules(self) -> list[RegisteredModule]:
        """按注册顺序返回全部模块。

        Returns:
            结果列表。
        """
        return list(self._modules.values())

    def iter_tools(self) -> Iterator[BaseTool]:
        """遍历工具。

        Returns:
            工具迭代器。
        """
        for registered in self._modules.values():
            yield from registered.runtime.agent_tools

    def iter_connector_registrations(self) -> Iterator[ConnectorRegistration]:
        """遍历连接器。

        Returns:
            连接器注册信息迭代器。
        """
        for registered in self._modules.values():
            yield from registered.runtime.connector_registrations

    def iter_workflows(self) -> Iterator[type[object]]:
        """遍历模块。

        Returns:
            工作流类型迭代器。
        """
        for registered in self._modules.values():
            yield from registered.runtime.temporal_workflows

    def iter_activities(self) -> Iterator[Callable[..., object]]:
        """遍历活动。

        Returns:
            活动可调用对象迭代器。
        """
        for registered in self._modules.values():
            yield from registered.runtime.temporal_activities

    def event_handlers(self) -> dict[str, EventHandler]:
        """处理事件。

        Returns:
            结构化结果字典。

        Raises:
            ModuleRegistrationError: 操作无法完成时抛出。
        """
        handlers: dict[str, EventHandler] = {}
        for registered in self._modules.values():
            for event_name, handler in registered.runtime.event_handlers.items():
                if event_name in handlers:
                    raise ModuleRegistrationError(f"duplicate event handler: {event_name}")
                handlers[event_name] = handler
        return handlers

    async def run_startup_hooks(self) -> None:
        """运行模块。

        Raises:
            ModuleRegistrationError: 操作无法完成时抛出。
        """
        for registered in self._modules.values():
            for hook in registered.runtime.startup_hooks:
                if not callable(hook):
                    raise ModuleRegistrationError(
                        f"module {registered.manifest.name} contains a non-callable startup hook"
                    )
                await hook()

    def deprecated_modules(self) -> tuple[ModuleManifest, ...]:
        """处理模块。

        Returns:
            结果元组。
        """
        return tuple(
            registered.manifest
            for registered in self._modules.values()
            if registered.manifest.deprecated
        )

    def iter_metric_providers(self) -> Iterator[MetricProvider]:
        """遍历提供方。

        Returns:
            指标提供方迭代器。
        """
        for registered in self._modules.values():
            yield from registered.runtime.metric_providers

    def mount_routes(self, app: FastAPI) -> None:
        """将模块路由挂载到统一的模块前缀。

        Args:
            app: 应用。
        """
        for registered in self._modules.values():
            runtime = registered.runtime
            if runtime.router is not None:
                app.include_router(runtime.router, prefix=registered.manifest.api_prefix)
            for legacy_router in runtime.legacy_routers:
                app.include_router(legacy_router)

    def _validate_route_conflicts(
        self,
        manifest: ModuleManifest,
        runtime: ModuleRuntime,
    ) -> None:
        """校验路由。

        Args:
            manifest: 模块或资源清单。
            runtime: 运行时容器。

        Raises:
            ModuleRegistrationError: 操作无法完成时抛出。
        """
        keys = self._route_keys_for(manifest, runtime)
        duplicates = sorted(keys & self._route_keys)
        if duplicates:
            method, path = duplicates[0]
            raise ModuleRegistrationError(
                f"route already registered for module {manifest.name}: {method} {path}"
            )

    def _claim_route_keys(
        self,
        manifest: ModuleManifest,
        runtime: ModuleRuntime,
    ) -> None:
        """处理报销单路由键。

        Args:
            manifest: 模块或资源清单。
            runtime: 运行时容器。
        """
        self._route_keys.update(self._route_keys_for(manifest, runtime))

    @staticmethod
    def _route_keys_for(
        manifest: ModuleManifest,
        runtime: ModuleRuntime,
    ) -> set[tuple[str, str]]:
        """路由键用于。

        Args:
            manifest: 模块或资源清单。
            runtime: 运行时容器。

        Returns:
            设置结果。
        """
        keys: set[tuple[str, str]] = set()
        if runtime.router is not None:
            for route in runtime.router.routes:
                path = getattr(route, "path", "")
                for method in getattr(route, "methods", ()) or ():
                    keys.add((method.upper(), f"{manifest.api_prefix}{path}"))
        for legacy_router in runtime.legacy_routers:
            for route in legacy_router.routes:
                path = getattr(route, "path", "")
                for method in getattr(route, "methods", ()) or ():
                    keys.add((method.upper(), path))
        return keys

    @staticmethod
    def _parse_version(value: str) -> tuple[int, int, int]:
        """解析版本。

        Args:
            value: 待处理值。

        Returns:
            结果元组。

        Raises:
            ModuleRegistrationError: 操作无法完成时抛出。
        """
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value)
        if match is None:
            raise ModuleRegistrationError(f"invalid platform version: {value!r}")
        return tuple(int(part) for part in match.groups())  # type: ignore[return-value]

    def _validate_manifest(self, manifest: ModuleManifest, *, check_global: bool = True) -> None:
        """校验清单。

        Args:
            manifest: 模块或资源清单。
            check_global: 检查全局。

        Raises:
            ModuleRegistrationError: 操作无法完成时抛出。
        """
        if not _NAME_PATTERN.fullmatch(manifest.name):
            raise ModuleRegistrationError(f"invalid module name: {manifest.name!r}")
        if not _VERSION_PATTERN.fullmatch(manifest.version):
            raise ModuleRegistrationError(f"invalid module version: {manifest.version!r}")
        if manifest.contract_version not in self._supported_contract_versions:
            raise ModuleRegistrationError(
                f"unsupported contract_version for {manifest.name}: {manifest.contract_version}"
            )
        if not _VERSION_PATTERN.fullmatch(manifest.minimum_platform_version):
            raise ModuleRegistrationError(
                f"invalid minimum_platform_version for {manifest.name}: "
                f"{manifest.minimum_platform_version!r}"
            )
        if self._parse_version(manifest.minimum_platform_version) > self._platform_version:
            raise ModuleRegistrationError(
                f"module {manifest.name} requires platform {manifest.minimum_platform_version}, "
                f"current platform is {'.'.join(map(str, self._platform_version))}"
            )
        if manifest.deprecated and not manifest.deprecation_message.strip():
            raise ModuleRegistrationError(
                f"deprecated module {manifest.name} must declare deprecation_message"
            )
        if not _API_PREFIX_PATTERN.fullmatch(manifest.api_prefix):
            raise ModuleRegistrationError(f"invalid api_prefix: {manifest.api_prefix!r}")
        if check_global and manifest.api_prefix in self._api_prefixes:
            raise ModuleRegistrationError(f"api_prefix already registered: {manifest.api_prefix}")
        if not _TASK_QUEUE_PATTERN.fullmatch(manifest.task_queue):
            raise ModuleRegistrationError(f"invalid task_queue: {manifest.task_queue!r}")
        if check_global and manifest.task_queue in self._task_queues:
            raise ModuleRegistrationError(f"task_queue already registered: {manifest.task_queue}")

        seen_permissions: set[str] = set()
        for permission in manifest.permissions:
            if permission in seen_permissions:
                raise ModuleRegistrationError(
                    f"duplicate permission in manifest {manifest.name}: {permission}"
                )
            if not _PERMISSION_PATTERN.fullmatch(permission):
                raise ModuleRegistrationError(f"invalid permission: {permission!r}")
            if not permission.startswith(f"{manifest.name}."):
                raise ModuleRegistrationError(
                    f"permission {permission!r} must start with {manifest.name!r}"
                )
            if check_global and permission in self._permissions:
                raise ModuleRegistrationError(f"permission already registered: {permission}")
            seen_permissions.add(permission)

        seen_published: set[str] = set()
        for event_name in manifest.published_events:
            if event_name in seen_published:
                raise ModuleRegistrationError(
                    f"duplicate published event in manifest {manifest.name}: {event_name}"
                )
            if not _EVENT_PATTERN.fullmatch(event_name):
                raise ModuleRegistrationError(f"invalid event name: {event_name!r}")
            if not event_name.startswith(f"{manifest.name}."):
                raise ModuleRegistrationError(
                    f"published event {event_name!r} must start with {manifest.name!r}"
                )
            if check_global and event_name in self._published_events:
                raise ModuleRegistrationError(f"event already registered: {event_name}")
            seen_published.add(event_name)

        for event_name in manifest.consumed_events:
            if not _EVENT_PATTERN.fullmatch(event_name):
                raise ModuleRegistrationError(f"invalid consumed event name: {event_name!r}")

        seen_dependencies: set[str] = set()
        for dependency in manifest.depends_on:
            if dependency in seen_dependencies:
                raise ModuleRegistrationError(f"duplicate dependency: {dependency}")
            if not dependency.startswith("core."):
                raise ModuleRegistrationError(
                    f"module dependency must reference core capability: {dependency!r}"
                )
            if dependency not in self._available_core_capabilities:
                raise ModuleRegistrationError(f"unknown core capability: {dependency!r}")
            seen_dependencies.add(dependency)

        if manifest.config_schema is not None:
            if not isinstance(manifest.config_schema, type) or not issubclass(
                manifest.config_schema, BaseModel
            ):
                raise ModuleRegistrationError(
                    f"config_schema for {manifest.name} must be a Pydantic BaseModel subclass"
                )
            if manifest.config_defaults:
                try:
                    manifest.config_schema.model_validate(dict(manifest.config_defaults))
                except ValidationError as exc:
                    raise ModuleRegistrationError(
                        f"invalid config_defaults for module {manifest.name}: {exc}"
                    ) from exc
        elif manifest.config_defaults:
            raise ModuleRegistrationError(
                f"module {manifest.name} declares config_defaults without config_schema"
            )
        if manifest.migration_namespace is not None and not _MIGRATION_NAMESPACE_PATTERN.fullmatch(
            manifest.migration_namespace
        ):
            raise ModuleRegistrationError(
                f"invalid migration_namespace: {manifest.migration_namespace!r}"
            )

    def _validate_context(self, manifest: ModuleManifest, context: ModuleContext) -> None:
        """校验上下文。

        Args:
            manifest: 模块或资源清单。
            context: 执行上下文。

        Raises:
            ModuleRegistrationError: 操作无法完成时抛出。
        """
        if "core.persistence" in manifest.depends_on and context.persistence is None:
            raise ModuleRegistrationError(
                f"module {manifest.name} depends on core.persistence but "
                "no persistence port is available"
            )
        if "core.object_store" in manifest.depends_on and context.object_store is None:
            raise ModuleRegistrationError(
                f"module {manifest.name} depends on core.object_store but "
                "no object store port is available"
            )
        if "core.cost" in manifest.depends_on and context.cost is None:
            raise ModuleRegistrationError(
                f"module {manifest.name} depends on core.cost but no cost port is available"
            )
        if "core.evaluation" in manifest.depends_on and context.evaluation is None:
            raise ModuleRegistrationError(
                f"module {manifest.name} depends on core.evaluation but "
                "no evaluation port is available"
            )
        if "core.identity" in manifest.depends_on and context.identity is None:
            raise ModuleRegistrationError(
                f"module {manifest.name} depends on core.identity but no identity port is available"
            )

    def _validate_config(
        self,
        manifest: ModuleManifest,
        context: ModuleContext,
    ) -> BaseModel | None:
        """校验配置。

        Args:
            manifest: 模块或资源清单。
            context: 执行上下文。

        Returns:
            基础模型无结果。

        Raises:
            ModuleRegistrationError: 操作无法完成时抛出。
        """
        if manifest.config_schema is None:
            return None
        try:
            return manifest.config_schema.model_validate(dict(context.config.values))
        except ValidationError as exc:
            raise ModuleRegistrationError(
                f"invalid config for module {manifest.name}: {exc}"
            ) from exc

    def _validate_runtime(
        self,
        manifest: ModuleManifest,
        runtime: ModuleRuntime,
        *,
        check_global: bool = True,
    ) -> None:
        """校验运行时。

        Args:
            manifest: 模块或资源清单。
            runtime: 运行时容器。
            check_global: 检查全局。

        Raises:
            ModuleRegistrationError: 操作无法完成时抛出。
        """
        if runtime.router is not None and not isinstance(runtime.router, APIRouter):
            raise ModuleRegistrationError(f"module {manifest.name} router must be an APIRouter")
        if runtime.router is not None and runtime.router.prefix:
            raise ModuleRegistrationError(
                f"module {manifest.name} router.prefix must be empty; "
                "use ModuleManifest.api_prefix"
            )

        for legacy_router in runtime.legacy_routers:
            if not isinstance(legacy_router, APIRouter):
                raise ModuleRegistrationError(
                    f"module {manifest.name} legacy router must be an APIRouter"
                )
            if legacy_router.prefix != "/v1" and not legacy_router.prefix.startswith("/v1/"):
                raise ModuleRegistrationError(
                    f"module {manifest.name} legacy router prefix must start with /v1/"
                )

        tool_names: set[str] = set()
        for tool in runtime.agent_tools:
            if not isinstance(tool, BaseTool):
                raise ModuleRegistrationError(
                    f"module {manifest.name} contains a non-BaseTool agent tool"
                )
            if tool.name in tool_names:
                raise ModuleRegistrationError(
                    f"duplicate tool name in module {manifest.name}: {tool.name}"
                )
            if check_global and tool.name in self._tool_names:
                raise ModuleRegistrationError(f"tool name already registered: {tool.name}")
            tool_names.add(tool.name)

        connector_ids: set[str] = set()
        for registration in runtime.connector_registrations:
            if not isinstance(registration, ConnectorRegistration):
                raise ModuleRegistrationError(
                    f"module {manifest.name} contains a non-ConnectorRegistration connector"
                )
            if registration.config_schema is not None:
                if not isinstance(registration.config_schema, type) or not issubclass(
                    registration.config_schema, BaseModel
                ):
                    raise ModuleRegistrationError(
                        f"connector {registration.connector_id} config_schema must be "
                        "a Pydantic BaseModel subclass"
                    )
            if registration.connector_id in connector_ids:
                raise ModuleRegistrationError(
                    f"duplicate connector id in module {manifest.name}: "
                    f"{registration.connector_id}"
                )
            if check_global and registration.connector_id in self._connector_ids:
                raise ModuleRegistrationError(
                    f"connector id already registered: {registration.connector_id}"
                )
            connector_ids.add(registration.connector_id)

        workflow_names: set[str] = set()
        for workflow in runtime.temporal_workflows:
            workflow_name = getattr(workflow, "__name__", "")
            if not isinstance(workflow, type) or not workflow_name:
                raise ModuleRegistrationError(
                    f"module {manifest.name} contains an invalid Temporal workflow"
                )
            if workflow_name in workflow_names:
                raise ModuleRegistrationError(
                    f"duplicate workflow name in module {manifest.name}: {workflow_name}"
                )
            if check_global and workflow_name in self._workflow_names:
                raise ModuleRegistrationError(f"workflow name already registered: {workflow_name}")
            workflow_names.add(workflow_name)

        for activity in runtime.temporal_activities:
            if not callable(activity):
                raise ModuleRegistrationError(
                    f"module {manifest.name} contains a non-callable Temporal activity"
                )

        for event_name, handler in runtime.event_handlers.items():
            if not _EVENT_PATTERN.fullmatch(event_name):
                raise ModuleRegistrationError(
                    f"invalid event handler key in module {manifest.name}: {event_name!r}"
                )
            if not callable(handler):
                raise ModuleRegistrationError(
                    f"event handler for {event_name!r} in module {manifest.name} is not callable"
                )
