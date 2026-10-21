"""测试模块目录测试模块。"""

from __future__ import annotations

import pytest

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.settings import Settings, get_settings


def test_enabled_module_names_are_normalized() -> None:
    """验证启用模块名称为对应的测试场景。"""
    settings = Settings(enabled_modules=" Expense, support,expense ")
    assert settings.enabled_module_names == ("expense", "support")


def test_app_registers_only_enabled_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证应用注册启用模块对应的测试场景。

    Args:
        monkeypatch: pytest 提供的猴子补丁对象。
    """
    monkeypatch.setenv("AGENTFORGE_ENABLED_MODULES", "expense")
    get_settings.cache_clear()
    try:
        app = create_platform_app()
        names = [module.manifest.name for module in app.state.module_registry.list_modules()]
        assert names == ["expense"]
    finally:
        get_settings.cache_clear()


def test_unknown_enabled_module_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证未知启用模块失败对应的测试场景。

    Args:
        monkeypatch: pytest 提供的猴子补丁对象。
    """
    monkeypatch.setenv("AGENTFORGE_ENABLED_MODULES", "support,unknown")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="unknown enabled modules"):
            create_platform_app()
    finally:
        get_settings.cache_clear()
