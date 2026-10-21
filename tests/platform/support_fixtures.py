"""客服测试模块。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.bootstrap import build_support_module
from agentforge.platform.infrastructure.memory_reply_connector import MemoryReplyConnector
from agentforge.platform.modules.support.infrastructure.memory_repository import (
    MemoryTicketRepository,
)
from agentforge.platform.modules.support.infrastructure.sqlalchemy_repository import (
    SQLAlchemyTicketRepository,
)
from agentforge.platform.modules.support.ports import ReplyConnectorPort
from agentforge.platform.modules.support.runtime import SupportRuntime, get_support_runtime
from agentforge.platform.runtime import ServiceContainer, build_module_context


def configure_memory_support(
    container: ServiceContainer,
    *,
    reply_connector: ReplyConnectorPort | None = None,
) -> SupportRuntime:
    """配置记忆客服。

    Args:
        container: 服务容器。
        reply_connector: 回复连接器。

    Returns:
        客服运行时结果。
    """
    module = build_support_module(
        container,
        ticket_repository=MemoryTicketRepository(),
        reply_connector=reply_connector or MemoryReplyConnector(),
    )
    module.build(build_module_context(container))
    return get_support_runtime()


def configure_sqlalchemy_support(
    container: ServiceContainer,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    reply_connector: ReplyConnectorPort | None = None,
) -> SupportRuntime:
    """配置SQLAlchemy客服。

    Args:
        container: 服务容器。
        session_factory: 数据库会话工厂。
        reply_connector: 回复连接器。

    Returns:
        客服运行时结果。
    """
    module = build_support_module(
        container,
        ticket_repository=SQLAlchemyTicketRepository(session_factory),
        reply_connector=reply_connector,
    )
    module.build(build_module_context(container))
    return get_support_runtime()


def create_app_with_support(container: ServiceContainer, support: SupportRuntime):
    """创建应用使用客服。

    Args:
        container: 服务容器。
        support: 客服。

    Returns:
        处理结果。
    """
    return create_platform_app(
        container,
        support_ticket_repository=support.repository,
        support_reply_connector=support.reply_connector,
        support_notification_gateway=support.notification_gateway,
    )
