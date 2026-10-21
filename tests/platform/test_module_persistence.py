"""测试模块持久化测试模块。"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agentforge.platform.infrastructure.db.base import _apply_module_search_path
from agentforge.platform.infrastructure.persistence import SQLAlchemyPersistence
from agentforge.platform.module_schemas import module_schema_name


class _Session:
    """会话相关组件。"""

    def __init__(self, schema: str) -> None:
        """初始化会话。

        Args:
            schema: 结构。
        """
        self.info = {"module_schema": schema}


class _Dialect:
    """数据库方言相关组件。"""

    def __init__(self, name: str) -> None:
        """初始化数据库方言。

        Args:
            name: 资源或对象名称。
        """
        self.name = name


class _Connection:
    """连接相关组件。"""

    def __init__(self, dialect_name: str = "postgresql") -> None:
        """初始化连接。

        Args:
            dialect_name: 数据库方言名称。
        """
        self.dialect = _Dialect(dialect_name)
        self.statements: list[str] = []

    def exec_driver_sql(self, statement: str) -> None:
        """处理SQL。

        Args:
            statement: 输入参数。
        """
        self.statements.append(statement)


def test_reviewed_module_schema_names() -> None:
    """验证已审核模块结构名称对应的测试场景。"""
    assert module_schema_name("support") == "module_support"
    assert module_schema_name("expense") == "module_expense"
    with pytest.raises(ValueError):
        module_schema_name("../public")
    with pytest.raises(ValueError):
        module_schema_name("unknown")


def test_postgresql_module_session_sets_local_search_path() -> None:
    """验证PostgreSQL模块会话本地搜索路径对应的测试场景。"""
    connection = _Connection()
    _apply_module_search_path(_Session("module_expense"), None, connection)
    assert connection.statements == [
        'SET LOCAL search_path TO "module_expense", public',
    ]


def test_sqlite_module_session_skips_search_path() -> None:
    """验证SQLite模块会话跳过搜索路径对应的测试场景。"""
    connection = _Connection("sqlite")
    _apply_module_search_path(_Session("module_support"), None, connection)
    assert connection.statements == []


@pytest.mark.asyncio
async def test_module_session_factory_uses_same_engine() -> None:
    """验证模块会话工厂使用引擎对应的测试场景。"""
    engine = create_async_engine("sqlite+aiosqlite://")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    persistence = SQLAlchemyPersistence(factory)
    module_factory = persistence.session_factory_for("expense")
    async with module_factory() as session:
        assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
        assert session.info["module_schema"] == "module_expense"
    await engine.dispose()
