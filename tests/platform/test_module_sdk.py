"""测试模块SDK测试模块。"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.core.module_registry import ModuleRegistrationError, ModuleRegistry
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.modules.demo_asset.domain.asset import Asset
from agentforge.platform.modules.demo_asset.infrastructure.memory_repository import (
    MemoryAssetRepository,
)
from agentforge.platform.modules.demo_asset.infrastructure.sqlalchemy_repository import (
    SQLAlchemyAssetRepository,
)
from agentforge.platform.modules.demo_asset.module import DemoAssetModule
from agentforge.platform.plugin_loader import load_module_plugins
from agentforge.platform.runtime import build_memory_container, build_module_context
from agentforge.platform.sdk.contract_testing import run_module_contract_suite


@pytest.mark.asyncio
async def test_demo_asset_passes_reusable_module_contract_suite() -> None:
    """验证资产通过模块契约套件对应的测试场景。"""
    repository = MemoryAssetRepository()
    module = DemoAssetModule(repository=repository)
    context = build_module_context(build_memory_container(), module_name="asset")

    async def tenant_isolation_probe() -> None:
        """处理租户隔离探针。"""
        asset = Asset(
            asset_id="probe-asset",
            tenant_id="tenant-a",
            name="Probe",
            created_by="tester",
        )
        await repository.save(asset)
        assert await repository.get("tenant-a", "probe-asset") is not None
        assert await repository.get("tenant-b", "probe-asset") is None

    report = await run_module_contract_suite(
        module,
        context,
        tenant_isolation_probe=tenant_isolation_probe,
    )

    assert report.module_name == "asset"
    assert {"route_prefix", "permissions", "events", "tenant_isolation"} <= set(report.checks)
    assert not report.warnings


def test_third_party_module_registers_without_core_or_catalog_changes() -> None:
    """验证模块注册不包含核心或目录对应的测试场景。"""
    app = create_platform_app(extra_modules=(DemoAssetModule(),), load_plugins=False)
    names = [module.manifest.name for module in app.state.module_registry.list_modules()]
    assert names == ["support", "expense", "asset"]
    connectors = [
        item.connector_id for item in app.state.module_registry.iter_connector_registrations()
    ]
    assert "asset-directory" in connectors

    client = TestClient(app)
    created = client.post(
        "/v1/assets/assets",
        json={
            "tenant_id": "tenant-a",
            "name": "Brand kit",
            "category": "marketing",
            "created_by": "designer-1",
        },
    )
    assert created.status_code == 200
    asset_id = created.json()["asset_id"]

    own = client.get("/v1/assets/assets", params={"tenant_id": "tenant-a"})
    other = client.get("/v1/assets/assets", params={"tenant_id": "tenant-b"})
    assert own.status_code == 200
    assert [item["asset_id"] for item in own.json()["assets"]] == [asset_id]
    assert other.status_code == 200
    assert other.json()["assets"] == []
    assert (
        client.get(
            f"/v1/assets/assets/{asset_id}",
            params={"tenant_id": "tenant-b"},
        ).status_code
        == 404
    )

    disabled = client.put(
        "/v1/admin/tenants/tenant-a/modules/asset",
        json={"enabled": False, "actor_id": "ops-admin"},
    )
    assert disabled.status_code == 200
    blocked = client.post(
        "/v1/assets/assets",
        json={
            "tenant_id": "tenant-a",
            "name": "Blocked",
            "created_by": "designer-1",
        },
    )
    assert blocked.status_code == 403
    support = client.post(
        "/v1/support/events/im",
        json={
            "tenant_id": "tenant-a",
            "source": "feishu",
            "message_id": "asset-disabled-support-still-works",
            "text": "How do I use this product?",
        },
    )
    assert support.status_code == 200


def test_plugin_loader_materializes_entry_point_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证插件加载器条目点工厂对应的测试场景。

    Args:
        monkeypatch: pytest 提供的猴子补丁对象。
    """

    class FakeEntryPoint:
        """用于测试模块发现的模拟入口点。"""

        name = "asset-plugin"

        @staticmethod
        def load():
            """加载模拟条目点。

            Returns:
                处理结果。
            """
            return DemoAssetModule

    class FakeEntryPoints:
        """用于测试模块发现的入口点集合。"""

        @staticmethod
        def select(*, group: str):
            """选择模拟条目。

            Args:
                group: 输入参数。

            Returns:
                处理结果。
            """
            assert group == "agentforge.modules"
            return [FakeEntryPoint()]

    monkeypatch.setattr(
        "agentforge.platform.plugin_loader.entry_points",
        lambda: FakeEntryPoints(),
    )
    plugins = load_module_plugins()
    assert len(plugins) == 1
    assert plugins[0].manifest.name == "asset"


def test_module_version_compatibility_and_deprecation_policy() -> None:
    """验证模块版本及弃用策略对应的测试场景。"""
    module = DemoAssetModule()
    context = build_module_context(build_memory_container(), module_name="asset")

    too_new = ModuleRegistry(lambda _: context, platform_version="0.4.0")
    with pytest.raises(ModuleRegistrationError, match="requires platform"):
        too_new.register(module)

    deprecated_manifest = DemoAssetModule.manifest
    # 替换数据类以模拟模块发布方交付新清单的方式。
    from dataclasses import replace

    deprecated = DemoAssetModule()
    deprecated.manifest = replace(
        deprecated_manifest,
        deprecated=True,
        deprecation_message="Use asset-v2 after 2027-01-01",
        replacement_module="asset_v2",
    )
    registry = ModuleRegistry(lambda _: context)
    registry.register(deprecated)
    assert registry.deprecated_modules()[0].replacement_module == "asset_v2"

    invalid = DemoAssetModule()
    invalid.manifest = replace(deprecated_manifest, deprecated=True)
    with pytest.raises(ModuleRegistrationError, match="deprecation_message"):
        ModuleRegistry(lambda _: context).register(invalid)


@pytest.mark.asyncio
async def test_demo_asset_sqlalchemy_repository_is_tenant_scoped() -> None:
    """验证资产SQLAlchemy仓储是否租户按范围隔离对应的测试场景。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    repository = SQLAlchemyAssetRepository(session_factory)
    asset = Asset(
        asset_id="sql-asset",
        tenant_id="tenant-sql-a",
        name="Contract",
        created_by="tester",
    )
    await repository.save(asset)

    assert await repository.get("tenant-sql-a", "sql-asset") is not None
    assert await repository.get("tenant-sql-b", "sql-asset") is None
    assert [item.asset_id for item in await repository.list("tenant-sql-a")] == ["sql-asset"]
    assert await repository.list("tenant-sql-b") == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_copied_module_template_passes_contract_suite() -> None:
    """验证模块模板通过契约套件对应的测试场景。"""
    template_root = Path(__file__).resolve().parents[2] / "templates" / "module-template"
    sys.path.insert(0, str(template_root))
    importlib.invalidate_caches()
    try:
        template_module = importlib.import_module("agentforge_module_template.module")
        module = template_module.DemoAssetModule()
        context = build_module_context(build_memory_container(), module_name="asset")
        report = await run_module_contract_suite(module, context)
        assert report.module_name == "asset"
        assert "temporal" in report.checks
    finally:
        sys.path.remove(str(template_root))
        for name in list(sys.modules):
            if name == "agentforge_module_template" or name.startswith(
                "agentforge_module_template."
            ):
                del sys.modules[name]
