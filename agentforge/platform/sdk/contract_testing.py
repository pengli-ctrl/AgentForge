"""契约模块。"""

from __future__ import annotations

import inspect
import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from agentforge.platform.sdk.module import BusinessModule, ModuleContext, ModuleRuntime

TenantIsolationProbe = Callable[[], Awaitable[None]]

SUPPORTED_CORE_CAPABILITIES_V1 = frozenset(
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
_PERMISSION_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_EVENT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\.v[1-9][0-9]*$")


class ModuleContractError(ValueError):
    """模块契约错误相关组件。"""


@dataclass(frozen=True)
class ModuleContractReport:
    """模块契约报告相关组件。

    Attributes:
        module_name: 模块名称。
        checks: 字段值。
        warnings: 字段值。
    """

    module_name: str
    checks: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)


async def run_module_contract_suite(
    module: BusinessModule,
    context: ModuleContext,
    *,
    available_capabilities: Iterable[str] = SUPPORTED_CORE_CAPABILITIES_V1,
    tenant_isolation_probe: TenantIsolationProbe | None = None,
) -> ModuleContractReport:
    """运行模块契约套件。

    Args:
        module: 模块。
        context: 执行上下文。
        available_capabilities: 可用。
        tenant_isolation_probe: 租户隔离探针。

    Returns:
        模块契约报告结果。

    Raises:
        ModuleContractError: 操作无法完成时抛出。
    """
    errors: list[str] = []
    checks: list[str] = []
    warnings: list[str] = []
    manifest = module.manifest
    capabilities = frozenset(available_capabilities)

    if not _NAME_PATTERN.fullmatch(manifest.name):
        errors.append(f"invalid module name: {manifest.name!r}")
    allowed_prefixes = {f"/v1/{manifest.name}", f"/v1/{manifest.name}s"}
    if manifest.api_prefix not in allowed_prefixes:
        errors.append(f"api_prefix must be one of {sorted(allowed_prefixes)}")
    if not manifest.task_queue.startswith(f"{manifest.name}-"):
        errors.append("task_queue must start with the module name")
    if manifest.migration_namespace != manifest.name:
        errors.append("migration_namespace must equal the module name")
    if manifest.contract_version != 1:
        errors.append("template contract currently supports contract_version=1")
    checks.extend(("manifest", "route_prefix", "task_queue", "migration_namespace"))

    for permission in manifest.permissions:
        if not _PERMISSION_PATTERN.fullmatch(permission) or not permission.startswith(
            f"{manifest.name}."
        ):
            errors.append(f"invalid module-scoped permission: {permission!r}")
    checks.append("permissions")

    for event_name in (*manifest.published_events, *manifest.consumed_events):
        if not _EVENT_PATTERN.fullmatch(event_name):
            errors.append(f"invalid event declaration: {event_name!r}")
    checks.append("events")

    for dependency in manifest.depends_on:
        if dependency not in capabilities:
            errors.append(f"unknown or unavailable core capability: {dependency!r}")
    checks.append("dependency_capabilities")

    if manifest.config_schema is not None:
        if not isinstance(manifest.config_schema, type) or not issubclass(
            manifest.config_schema, BaseModel
        ):
            errors.append("config_schema must be a Pydantic BaseModel subclass")
        elif manifest.config_defaults:
            try:
                manifest.config_schema.model_validate(dict(manifest.config_defaults))
            except ValidationError as exc:
                errors.append(f"config_defaults do not match config_schema: {exc}")
    checks.append("config_schema")

    runtime = module.build(context)
    if not isinstance(runtime, ModuleRuntime):
        errors.append("module.build() must return ModuleRuntime")
        runtime = ModuleRuntime()
    if runtime.router is None:
        errors.append("module must expose a standard APIRouter")
    else:
        if runtime.router.prefix:
            errors.append("module router.prefix must be empty; use manifest.api_prefix")
        for route in runtime.router.routes:
            path = str(getattr(route, "path", ""))
            if not path.startswith("/"):
                errors.append(f"module route must start with '/': {path!r}")
            for method in getattr(route, "methods", ()) or ():
                if method.upper() in {"POST", "PUT", "PATCH", "DELETE", "GET"}:
                    checks.append(f"route:{method.upper()} {path}")
    checks.append("runtime_routes")

    for event_name, handler in runtime.event_handlers.items():
        if not _EVENT_PATTERN.fullmatch(event_name) or not callable(handler):
            errors.append(f"invalid event handler: {event_name!r}")
    if not runtime.event_handlers:
        errors.append("module must declare at least one event handler for the template contract")
    checks.append("event_handlers")

    if not runtime.startup_hooks or not all(
        inspect.iscoroutinefunction(hook) or callable(hook) for hook in runtime.startup_hooks
    ):
        errors.append("module must expose a callable startup hook")
    checks.append("startup_hook")

    if not runtime.temporal_workflows:
        errors.append("module must expose at least one Temporal workflow")
    if not runtime.temporal_activities:
        errors.append("module must expose at least one Temporal activity")
    checks.append("temporal")

    if manifest.deprecated and not manifest.deprecation_message.strip():
        errors.append("deprecated modules must declare deprecation_message")
    checks.append("version_policy")

    if tenant_isolation_probe is not None:
        try:
            await tenant_isolation_probe()
        except Exception as exc:  # noqa: BLE001 - surfaced as contract evidence
            errors.append(f"tenant isolation probe failed: {exc}")
        checks.append("tenant_isolation")
    else:
        warnings.append("tenant_isolation probe not supplied")

    if errors:
        raise ModuleContractError("; ".join(errors))
    return ModuleContractReport(
        module_name=manifest.name,
        checks=tuple(dict.fromkeys(checks)),
        warnings=tuple(warnings),
    )


__all__ = [
    "ModuleContractError",
    "ModuleContractReport",
    "SUPPORTED_CORE_CAPABILITIES_V1",
    "TenantIsolationProbe",
    "run_module_contract_suite",
]
