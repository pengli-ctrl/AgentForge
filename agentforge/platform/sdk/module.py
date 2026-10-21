"""模块。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from fastapi import APIRouter
from pydantic import BaseModel

from agentforge.core.base_tool import BaseTool
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.sdk.connector import ConnectorRegistration
from agentforge.platform.sdk.ports import (
    AuditPort,
    AuthenticatorPort,
    AuthorizationPort,
    ChunkedUploadPort,
    ConnectorCatalogPort,
    CostPort,
    EvaluationPort,
    KnowledgePort,
    ModelGatewayPort,
    ModuleAccessPort,
    ObjectStorePort,
    OcrPort,
    OutboxPort,
    PersistencePort,
    PolicyPort,
    RbacPort,
    TenantConfigPort,
    UsagePort,
    WorkflowClientPort,
)

EventHandler = Callable[[EventEnvelope], Awaitable[None]]
StartupHook = Callable[[], Awaitable[None]]
MetricProvider = Callable[[], Awaitable[str]]


@dataclass(frozen=True)
class TenantContext:
    """请求或任务范围内的租户上下文。

    Attributes:
        tenant_id: 租户 ID，用于数据隔离。
    """

    tenant_id: str


@dataclass(frozen=True)
class ModuleConfig:
    """模块级静态配置。

    Attributes:
        values: 值。
    """

    values: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ModuleManifest:
    """模块元数据与契约声明。

    Attributes:
        name: 名称。
        version: 版本号。
        api_prefix: API前缀。
        task_queue: 任务队列。
        contract_version: 契约版本。
        depends_on: 时。
        permissions: 权限。
        published_events: 已发布事件。
        consumed_events: 事件。
        config_schema: 配置结构。
        config_defaults: 配置默认项。
        migration_namespace: 迁移。
        enabled_by_default: 启用由默认。
        minimum_platform_version: 平台版本。
        deprecated: 字段值。
        deprecation_message: 弃用。
        replacement_module: 模块。
    """

    name: str
    version: str
    api_prefix: str
    task_queue: str
    contract_version: int = 1
    depends_on: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    published_events: tuple[str, ...] = ()
    consumed_events: tuple[str, ...] = ()
    config_schema: type[BaseModel] | None = None
    config_defaults: Mapping[str, object] = field(default_factory=dict)
    migration_namespace: str | None = None
    enabled_by_default: bool = False
    minimum_platform_version: str = "0.1.0"
    deprecated: bool = False
    deprecation_message: str = ""
    replacement_module: str | None = None


@dataclass(frozen=True)
class ModuleContext:
    """模块构建时注入的平台端口。

    Attributes:
        audit: 审计。
        authorization: 授权。
        outbox: Outbox。
        connectors: 连接器。
        knowledge: 知识。
        models: 数据模型。
        policy: 策略。
        cost: 成本。
        evaluation: 评估。
        identity: 字段值。
        module_access: 模块访问。
        workflow: 工作流。
        persistence: 持久化。
        ocr: OCR。
        object_store: 对象存储。
        uploads: 上传。
        config: 组件配置。
        tenant_config: 租户配置。
        authenticator: 认证器。
        usage: 用量。
    """

    audit: AuditPort
    authorization: AuthorizationPort
    outbox: OutboxPort
    connectors: ConnectorCatalogPort
    knowledge: KnowledgePort
    models: ModelGatewayPort
    policy: PolicyPort
    cost: CostPort
    evaluation: EvaluationPort | None
    identity: RbacPort
    module_access: ModuleAccessPort
    workflow: WorkflowClientPort | None = None
    persistence: PersistencePort | None = None
    ocr: OcrPort | None = None
    object_store: ObjectStorePort | None = None
    uploads: ChunkedUploadPort | None = None
    config: ModuleConfig = field(default_factory=ModuleConfig)
    tenant_config: TenantConfigPort | None = None
    authenticator: AuthenticatorPort | None = None
    usage: UsagePort | None = None


@dataclass
class ModuleRuntime:
    """模块向平台注册的运行时能力。

    Attributes:
        router: 路由。
        legacy_routers: 旧版。
        temporal_workflows: Temporal。
        temporal_activities: Temporal活动。
        agent_tools: 智能体工具。
        connector_registrations: 连接器。
        event_handlers: 事件。
        startup_hooks: 字段值。
        metric_providers: 提供方。
    """

    router: APIRouter | None = None
    legacy_routers: list[APIRouter] = field(default_factory=list)
    temporal_workflows: list[type[object]] = field(default_factory=list)
    temporal_activities: list[Callable[..., object]] = field(default_factory=list)
    agent_tools: list[BaseTool] = field(default_factory=list)
    connector_registrations: list[ConnectorRegistration] = field(default_factory=list)
    event_handlers: dict[str, EventHandler] = field(default_factory=dict)
    startup_hooks: list[StartupHook] = field(default_factory=list)
    metric_providers: list[MetricProvider] = field(default_factory=list)


@runtime_checkable
class BusinessModule(Protocol):
    """业务模块必须实现的稳定协议。"""

    @property
    def manifest(self) -> ModuleManifest:
        """返回模块静态清单。

        Returns:
            模块清单结果。
        """
        ...

    def build(self, ctx: ModuleContext) -> ModuleRuntime:
        """使用平台端口构建模块运行时。

        Args:
            ctx: 执行上下文。

        Returns:
            模块运行时结果。
        """
        ...
