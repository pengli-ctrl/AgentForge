"""AgentForge 平台基础设施层：base。

本模块负责 base 相关的平台能力，是 平台基础设施层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：Base。
- 主要函数：create_engine、create_session_factory、session_scope。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base。

    Base 封装相关领域行为，保持职责单一并降低调用方复杂度。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    pass


def create_engine(database_url: str):
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        database_url: str，调用方传入的 database_url 参数。

    Returns:
        None，函数执行后的结果。
    """
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        database_url: str，调用方传入的 database_url 参数。

    Returns:
        async_sessionmaker[AsyncSession]，函数执行后的结果。
    """
    return async_sessionmaker(create_engine(database_url), expire_on_commit=False)


async def session_scope(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """执行 session_scope 对应的逻辑，并返回处理结果。

    Args:
        session_factory: async_sessionmaker[AsyncSession]，调用方传入的 session_factory 参数。

    Returns:
        AsyncIterator[AsyncSession]，函数执行后的结果。
    """
    async with session_factory() as session:
        yield session
