"""基础模块。"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session


@event.listens_for(Session, "after_begin")
def _apply_module_search_path(session: Session, transaction, connection) -> None:
    """应用模块搜索路径。

    Args:
        session: 当前会话。
        transaction: 输入参数。
        connection: 连接。

    Raises:
        ValueError: 输入值或业务状态不合法时抛出。
    """
    del transaction
    schema = session.info.get("module_schema")
    if not schema or connection.dialect.name != "postgresql":
        return
    if not str(schema).replace("_", "").isalnum():
        raise ValueError("invalid module schema")
    connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')


class Base(DeclarativeBase):
    """基础相关组件。"""

    pass


def create_engine(database_url: str):
    """创建引擎。

    Args:
        database_url: 数据库URL。

    Returns:
        处理结果。
    """
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    """创建会话工厂。

    Args:
        database_url: 数据库URL。

    Returns:
        异步结果。
    """
    return async_sessionmaker(create_engine(database_url), expire_on_commit=False)


async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """处理会话。

    Args:
        session_factory: 数据库会话工厂。

    Yields:
        逐次生成的结果。
    """
    async with session_factory() as session:
        yield session
