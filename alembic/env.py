"""AgentForge AgentForge 项目：env。

本模块负责 env 相关能力，是 AgentForge 项目 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要函数：run_migrations_offline、do_run_migrations、run_migrations_online。
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option(
    "sqlalchemy.url",
    os.environ.get(
        "AGENTFORGE_DATABASE_URL",
        "postgresql+asyncpg://agentforge:agentforge@localhost:5432/agentforge",
    ),
)
target_metadata = None


def run_migrations_offline() -> None:
    """执行完整流程，并返回调用方需要的结果。

    Returns:
        None，函数执行后的结果。
    """
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """执行 do_run_migrations 对应的逻辑，并返回处理结果。

    Args:
        connection: Any，调用方传入的 connection 参数。

    Returns:
        None，函数执行后的结果。
    """
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """执行完整流程，并返回调用方需要的结果。

    Returns:
        None，函数执行后的结果。
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
