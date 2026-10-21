"""运行时模块。"""

from __future__ import annotations

from dataclasses import dataclass

from agentforge.platform.modules.support.application.processing import (
    SupportTicketProcessingService,
)
from agentforge.platform.modules.support.application.service import SupportTicketService
from agentforge.platform.modules.support.application.writeback import TicketWritebackService
from agentforge.platform.modules.support.ports import (
    NotificationPort,
    ReplyConnectorPort,
    TicketRepository,
)
from agentforge.platform.sdk.ports import AuthenticatorPort, ModuleAccessPort, WorkflowClientPort


@dataclass(frozen=True)
class SupportRuntime:
    """客服运行时相关组件。

    Attributes:
        authenticator: 认证器。
        module_access: 模块访问。
        ticket_service: 工单服务。
        repository: 数据仓储实现。
        reply_connector: 回复连接器。
        notification_gateway: 通知网关。
        ticket_writeback_service: 工单写回服务。
        processing_service: 处理服务。
        workflow_client: 工作流客户端。
        webhook_secret: Webhook密钥。
    """

    authenticator: AuthenticatorPort
    module_access: ModuleAccessPort
    ticket_service: SupportTicketService
    repository: TicketRepository
    reply_connector: ReplyConnectorPort | None
    notification_gateway: NotificationPort | None
    ticket_writeback_service: TicketWritebackService
    processing_service: SupportTicketProcessingService
    workflow_client: WorkflowClientPort | None
    webhook_secret: str = ""


_runtime: SupportRuntime | None = None


def configure_support_runtime(runtime: SupportRuntime) -> None:
    """配置客服运行时。

    Args:
        runtime: 运行时容器。
    """
    global _runtime
    _runtime = runtime


def get_support_runtime() -> SupportRuntime:
    """获取客服运行时。

    Returns:
        客服运行时结果。

    Raises:
        RuntimeError: 运行时依赖或状态不满足要求时抛出。
    """
    if _runtime is None:
        raise RuntimeError("Support runtime has not been configured")
    return _runtime


def reset_support_runtime() -> None:
    """清理运行时，供测试隔离使用。"""
    global _runtime
    _runtime = None
