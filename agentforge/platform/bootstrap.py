"""启动装配模块。"""

from __future__ import annotations

from typing import cast

from agentforge.platform.modules.expense.module import ExpenseModule, ExpenseModuleDependencies
from agentforge.platform.modules.expense.ports import (
    ExpenseAttachmentRepository,
    ExpenseClaimRepository,
    ExpenseExtractionRepository,
    ExpenseImportBatchRepository,
    ExpenseInvoiceGateAlertRepository,
    ExpenseInvoiceRepository,
    ExpenseOcrJobRepository,
    ExpenseWritebackJobRepository,
)
from agentforge.platform.modules.support.module import SupportModule, SupportModuleDependencies
from agentforge.platform.modules.support.ports import (
    NotificationPort,
    ReplyConnectorPort,
    TicketRepository,
)
from agentforge.platform.runtime import (
    ServiceContainer,
    build_memory_container,
    configure_container,
    get_container,
)
from agentforge.platform.sdk.ports import AuthenticatorPort


def build_default_container() -> ServiceContainer:
    """构建默认共享容器。

    Returns:
        服务容器结果。
    """
    return build_memory_container()


def build_expense_module(
    container: ServiceContainer,
    *,
    claim_repository: ExpenseClaimRepository,
    attachment_repository: ExpenseAttachmentRepository,
    extraction_repository: ExpenseExtractionRepository,
    ocr_job_repository: ExpenseOcrJobRepository,
    import_batch_repository: ExpenseImportBatchRepository,
    writeback_job_repository: ExpenseWritebackJobRepository,
    invoice_repository: ExpenseInvoiceRepository,
    invoice_gate_alert_repository: ExpenseInvoiceGateAlertRepository,
) -> ExpenseModule:
    """构建报销模块。

    Args:
        container: 服务容器。
        claim_repository: 报销单仓储。
        attachment_repository: 附件仓储。
        extraction_repository: 提取仓储。
        ocr_job_repository: OCR任务仓储。
        import_batch_repository: 导入批次仓储。
        writeback_job_repository: 写回任务仓储。
        invoice_repository: 发票仓储。
        invoice_gate_alert_repository: 发票门禁告警仓储。
            alert repository。

    Returns:
        报销模块结果。
    """
    return ExpenseModule(
        ExpenseModuleDependencies(
            authenticator=cast(AuthenticatorPort, container.authenticator),
            claim_repository=claim_repository,
            attachment_repository=attachment_repository,
            extraction_repository=extraction_repository,
            ocr_job_repository=ocr_job_repository,
            import_batch_repository=import_batch_repository,
            writeback_job_repository=writeback_job_repository,
            invoice_repository=invoice_repository,
            invoice_gate_alert_repository=invoice_gate_alert_repository,
        )
    )


def build_support_module(
    container: ServiceContainer,
    *,
    ticket_repository: TicketRepository,
    reply_connector: ReplyConnectorPort | None = None,
    notification_gateway: NotificationPort | None = None,
    webhook_secret: str = "",
) -> SupportModule:
    """构建客服模块。

    Args:
        container: 服务容器。
        ticket_repository: 工单仓储。
        reply_connector: 回复连接器。
        notification_gateway: 通知网关。
        webhook_secret: Webhook密钥。

    Returns:
        客服模块结果。
    """
    return SupportModule(
        SupportModuleDependencies(
            authenticator=cast(AuthenticatorPort, container.authenticator),
            ticket_repository=ticket_repository,
            reply_connector=reply_connector,
            notification_gateway=notification_gateway,
            webhook_secret=webhook_secret,
        )
    )


__all__ = [
    "ServiceContainer",
    "build_default_container",
    "build_expense_module",
    "build_memory_container",
    "build_support_module",
    "configure_container",
    "get_container",
]
