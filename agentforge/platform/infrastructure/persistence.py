"""持久化模块。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.module_schemas import module_schema_name


class SQLAlchemyPersistence:
    """基于 SQLAlchemy 的持久化实现。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """初始化 SQLAlchemyPersistence。

        Args:
            session_factory: 数据库会话工厂。
        """
        self._session_factory = session_factory

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """返回会话工厂。

        Returns:
            异步结果。
        """
        return self._session_factory

    def session_factory_for(self, module_name: str) -> async_sessionmaker[AsyncSession]:
        """处理会话工厂用于。

        Args:
            module_name: 模块名称。

        Returns:
            异步结果。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        schema = module_schema_name(module_name)
        bind = self._session_factory.kw.get("bind")
        if bind is None:
            raise RuntimeError("SQLAlchemy session factory has no engine bind")
        return async_sessionmaker(
            bind=bind,
            expire_on_commit=False,
            info={"module_schema": schema},
        )
