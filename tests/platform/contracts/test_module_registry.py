"""ModuleRegistry 契约测试。

本文件只验证模块契约本身，不依赖任何具体业务模块。
"""

from __future__ import annotations

from typing import cast

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from agentforge.core.base_tool import BaseTool, ToolResult
from agentforge.platform.core.module_registry import ModuleRegistrationError, ModuleRegistry
from agentforge.platform.domain.connector import ConnectorKind
from agentforge.platform.sdk.connector import ConnectorRegistration
from agentforge.platform.sdk.module import (
    ModuleConfig,
    ModuleContext,
    ModuleManifest,
    ModuleRuntime,
)
from agentforge.platform.sdk.ports import (
    AuditPort,
    AuthorizationPort,
    ChunkedUploadPort,
    ConnectorCatalogPort,
    CostPort,
    EvaluationPort,
    KnowledgePort,
    ModelGatewayPort,
    ModuleAccessPort,
    ObjectStorePort,
    OutboxPort,
    PersistencePort,
    PolicyPort,
    RbacPort,
    WorkflowClientPort,
)


class FakeTool(BaseTool):
    """最小可注册工具。"""

    def __init__(self, name: str) -> None:
        """初始化模拟工具。

        Args:
            name: 资源或对象名称。
        """
        self._name = name

    @property
    def name(self) -> str:
        """返回对象名称。

        Returns:
            字符串结果。
        """
        return self._name

    def schema(self) -> dict:
        """返回工具参数的结构定义。

        Returns:
            结构化结果字典。
        """
        return {"name": self._name, "description": "fake tool"}

    async def execute(self, **kwargs: object) -> ToolResult:
        """执行模拟工具。

        Args:
            kwargs: 关键字参数。

        Returns:
            工具结果结果。
        """
        return ToolResult(success=True, output="")


class FakeModule:
    """用于契约测试的模块实现。"""

    def __init__(self, manifest: ModuleManifest, runtime: ModuleRuntime | None = None) -> None:
        """初始化模拟模块。

        Args:
            manifest: 模块或资源清单。
            runtime: 运行时容器。
        """
        self._manifest = manifest
        self._runtime = runtime or ModuleRuntime()

    @property
    def manifest(self) -> ModuleManifest:
        """返回清单。

        Returns:
            模块清单结果。
        """
        return self._manifest

    def build(self, ctx: ModuleContext) -> ModuleRuntime:
        """构建模拟模块。

        Args:
            ctx: 执行上下文。

        Returns:
            模块运行时结果。
        """
        return self._runtime


class ExpenseConfig(BaseModel):
    """测试用模块配置。

    Attributes:
        endpoint: 端点。
    """

    endpoint: str


def _context(config: ModuleConfig | None = None) -> ModuleContext:
    """处理上下文。

    Args:
        config: 组件配置。

    Returns:
        模块上下文结果。
    """
    return ModuleContext(
        audit=cast(AuditPort, object()),
        authorization=cast(AuthorizationPort, object()),
        outbox=cast(OutboxPort, object()),
        connectors=cast(ConnectorCatalogPort, object()),
        knowledge=cast(KnowledgePort, object()),
        models=cast(ModelGatewayPort, object()),
        policy=cast(PolicyPort, object()),
        cost=cast(CostPort, object()),
        evaluation=cast(EvaluationPort, object()),
        identity=cast(RbacPort, object()),
        module_access=cast(ModuleAccessPort, object()),
        workflow=cast(WorkflowClientPort, object()),
        persistence=cast(PersistencePort, object()),
        object_store=cast(ObjectStorePort, object()),
        uploads=cast(ChunkedUploadPort, object()),
        config=config or ModuleConfig(),
    )


def _manifest(**overrides: object) -> ModuleManifest:
    """处理清单。

    Args:
        overrides: 配置覆盖项。

    Returns:
        模块清单结果。
    """
    values: dict[str, object] = {
        "name": "expense",
        "version": "0.1.0",
        "api_prefix": "/v1/expense",
        "task_queue": "expense-copilot",
        "contract_version": 1,
        "depends_on": ("core.tenant", "core.audit"),
        "permissions": ("expense.document.read",),
        "published_events": ("expense.document.uploaded.v1",),
        "consumed_events": (),
    }
    values.update(overrides)
    return ModuleManifest(**values)  # type: ignore[arg-type]


def _registry(config: ModuleConfig | None = None) -> ModuleRegistry:
    """处理注册表。

    Args:
        config: 组件配置。

    Returns:
        模块注册表结果。
    """
    return ModuleRegistry(lambda _manifest: _context(config))


def test_register_module_and_mount_routes() -> None:
    """验证注册模块及路由对应的测试场景。"""
    router = APIRouter()

    @router.get("/documents")
    async def list_documents() -> list[str]:
        """处理 GET /documents 请求，查询文档。

        Returns:
            结果列表。
        """
        return []

    registry = _registry()
    registered = registry.register(FakeModule(_manifest(), ModuleRuntime(router=router)))

    assert registry.get("expense") is registered
    registry.validate()

    app = FastAPI()
    registry.mount_routes(app)
    response = TestClient(app).get("/v1/expense/documents")
    assert response.status_code == 200
    assert response.json() == []


def test_duplicate_module_name_is_rejected() -> None:
    """验证重复模块名称是否拒绝对应的测试场景。"""
    registry = _registry()
    registry.register(FakeModule(_manifest()))

    with pytest.raises(ModuleRegistrationError, match="module already registered"):
        registry.register(FakeModule(_manifest()))


@pytest.mark.parametrize("name", ["Expense", "expense-1", "", "1expense"])
def test_invalid_module_name_is_rejected(name: str) -> None:
    """验证无效模块名称是否拒绝对应的测试场景。

    Args:
        name: 资源或对象名称。
    """
    with pytest.raises(ModuleRegistrationError, match="invalid module name"):
        _registry().register(FakeModule(_manifest(name=name)))


@pytest.mark.parametrize("prefix", ["expense", "/v2/expense", "/v1/expense/", "/v1/expense//x"])
def test_invalid_api_prefix_is_rejected(prefix: str) -> None:
    """验证无效API前缀是否拒绝对应的测试场景。

    Args:
        prefix: 前缀。
    """
    with pytest.raises(ModuleRegistrationError, match="invalid api_prefix"):
        _registry().register(FakeModule(_manifest(api_prefix=prefix)))


def test_duplicate_api_prefix_is_rejected() -> None:
    """验证重复API前缀是否拒绝对应的测试场景。"""
    registry = _registry()
    registry.register(FakeModule(_manifest()))
    second = _manifest(
        name="claims",
        api_prefix="/v1/expense",
        task_queue="claims-copilot",
        permissions=("claims.document.read",),
        published_events=("claims.document.uploaded.v1",),
    )

    with pytest.raises(ModuleRegistrationError, match="api_prefix already registered"):
        registry.register(FakeModule(second))


@pytest.mark.parametrize(
    "permission",
    ["expense.read", "claims.document.read", "expense..read", ""],
)
def test_invalid_permission_is_rejected(permission: str) -> None:
    """验证无效权限是否拒绝对应的测试场景。

    Args:
        permission: 权限。
    """
    with pytest.raises(ModuleRegistrationError):
        _registry().register(FakeModule(_manifest(permissions=(permission,))))


@pytest.mark.parametrize("event_name", ["expense.document.uploaded", "claims.document.uploaded.v1"])
def test_invalid_published_event_is_rejected(event_name: str) -> None:
    """验证无效已发布事件是否拒绝对应的测试场景。

    Args:
        event_name: 事件名称。
    """
    with pytest.raises(ModuleRegistrationError):
        _registry().register(FakeModule(_manifest(published_events=(event_name,))))


def test_module_dependency_must_be_core_capability() -> None:
    """验证模块必须为核心能力对应的测试场景。"""
    with pytest.raises(ModuleRegistrationError, match="core capability"):
        _registry().register(FakeModule(_manifest(depends_on=("support.ticket",))))


def test_unknown_core_capability_is_rejected() -> None:
    """验证未知核心能力是否拒绝对应的测试场景。"""
    with pytest.raises(ModuleRegistrationError, match="unknown core capability"):
        _registry().register(FakeModule(_manifest(depends_on=("core.unknown",))))


def test_unsupported_contract_version_is_rejected() -> None:
    """验证不支持契约版本是否拒绝对应的测试场景。"""
    with pytest.raises(ModuleRegistrationError, match="unsupported contract_version"):
        _registry().register(FakeModule(_manifest(contract_version=2)))


def test_duplicate_task_queue_is_rejected() -> None:
    """验证重复任务队列是否拒绝对应的测试场景。"""
    registry = _registry()
    registry.register(FakeModule(_manifest()))
    second = _manifest(
        name="claims",
        api_prefix="/v1/claims",
        permissions=("claims.document.read",),
        published_events=("claims.document.uploaded.v1",),
    )

    with pytest.raises(ModuleRegistrationError, match="task_queue already registered"):
        registry.register(FakeModule(second))


def test_duplicate_tool_name_across_modules_is_rejected() -> None:
    """验证重复工具名称跨模块是否拒绝对应的测试场景。"""
    registry = _registry()
    registry.register(FakeModule(_manifest(), ModuleRuntime(agent_tools=[FakeTool("lookup")])))
    second = _manifest(
        name="claims",
        api_prefix="/v1/claims",
        task_queue="claims-copilot",
        permissions=("claims.document.read",),
        published_events=("claims.document.uploaded.v1",),
    )

    with pytest.raises(ModuleRegistrationError, match="tool name already registered"):
        registry.register(FakeModule(second, ModuleRuntime(agent_tools=[FakeTool("lookup")])))


def test_router_prefix_must_be_empty() -> None:
    """验证路由前缀必须为空对应的测试场景。"""
    with pytest.raises(ModuleRegistrationError, match="router.prefix must be empty"):
        _registry().register(
            FakeModule(_manifest(), ModuleRuntime(router=APIRouter(prefix="/expense")))
        )


def test_config_schema_is_validated() -> None:
    """验证配置结构是否已验证对应的测试场景。"""
    config = ModuleConfig(values={"endpoint": "https://erp.example.com"})
    manifest = _manifest(config_schema=ExpenseConfig)
    registered = _registry(config).register(FakeModule(manifest))

    assert registered.validated_config == ExpenseConfig(endpoint="https://erp.example.com")


def test_invalid_config_is_rejected() -> None:
    """验证无效配置是否拒绝对应的测试场景。"""
    with pytest.raises(ModuleRegistrationError, match="invalid config"):
        _registry(ModuleConfig()).register(FakeModule(_manifest(config_schema=ExpenseConfig)))


def test_duplicate_connector_id_is_rejected() -> None:
    """验证重复连接器ID是否拒绝对应的测试场景。"""
    registry = _registry()
    first = ConnectorRegistration(
        connector_id="erp",
        name="erp",
        kind=ConnectorKind.OPENAPI,
    )
    registry.register(FakeModule(_manifest(), ModuleRuntime(connector_registrations=[first])))
    second = _manifest(
        name="claims",
        api_prefix="/v1/claims",
        task_queue="claims-copilot",
        permissions=("claims.document.read",),
        published_events=("claims.document.uploaded.v1",),
    )

    with pytest.raises(ModuleRegistrationError, match="connector id already registered"):
        registry.register(
            FakeModule(
                second,
                ModuleRuntime(
                    connector_registrations=[
                        ConnectorRegistration(
                            connector_id="erp",
                            name="erp",
                            kind=ConnectorKind.OPENAPI,
                        )
                    ]
                ),
            )
        )


def test_legacy_router_is_mounted_at_root() -> None:
    """验证旧版路由是否于根对应的测试场景。"""
    legacy = APIRouter(prefix="/v1/legacy")

    @legacy.get("/ping")
    async def legacy_ping() -> dict[str, str]:
        """处理 GET /ping 请求，查询旧版探活。

        Returns:
            结构化结果字典。
        """
        return {"status": "ok"}

    registry = _registry()
    registry.register(FakeModule(_manifest(), ModuleRuntime(legacy_routers=[legacy])))
    app = FastAPI()
    registry.mount_routes(app)

    response = TestClient(app).get("/v1/legacy/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("prefix", ["", "/legacy", "/v2/legacy"])
def test_invalid_legacy_router_prefix_is_rejected(prefix: str) -> None:
    """验证无效旧版路由前缀是否拒绝对应的测试场景。

    Args:
        prefix: 前缀。
    """
    with pytest.raises(ModuleRegistrationError, match="legacy router prefix"):
        _registry().register(
            FakeModule(
                _manifest(),
                ModuleRuntime(legacy_routers=[APIRouter(prefix=prefix)]),
            )
        )


def test_duplicate_legacy_route_is_rejected_across_modules() -> None:
    """验证重复旧版路由是否拒绝跨模块对应的测试场景。"""
    first_legacy = APIRouter(prefix="/v1/shared")

    @first_legacy.get("/ping")
    async def first_ping() -> dict[str, str]:
        """处理 GET /ping 请求，查询第一探活。

        Returns:
            结构化结果字典。
        """
        return {"owner": "expense"}

    second_legacy = APIRouter(prefix="/v1/shared")

    @second_legacy.get("/ping")
    async def second_ping() -> dict[str, str]:
        """处理 GET /ping 请求，查询第二探活。

        Returns:
            结构化结果字典。
        """
        return {"owner": "claims"}

    registry = _registry()
    registry.register(FakeModule(_manifest(), ModuleRuntime(legacy_routers=[first_legacy])))
    second = _manifest(
        name="claims",
        api_prefix="/v1/claims",
        task_queue="claims-copilot",
        permissions=("claims.document.read",),
        published_events=("claims.document.uploaded.v1",),
    )

    with pytest.raises(ModuleRegistrationError, match="route already registered"):
        registry.register(FakeModule(second, ModuleRuntime(legacy_routers=[second_legacy])))
