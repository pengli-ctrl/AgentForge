"""模块目录模块。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.bootstrap import build_expense_module, build_support_module
from agentforge.platform.infrastructure.memory_reply_connector import MemoryReplyConnector
from agentforge.platform.modules.expense.infrastructure.memory_attachment_repository import (
    MemoryExpenseAttachmentRepository,
)
from agentforge.platform.modules.expense.infrastructure.memory_extraction_repository import (
    MemoryExpenseExtractionRepository,
)
from agentforge.platform.modules.expense.infrastructure.memory_import_batch_repository import (
    MemoryExpenseImportBatchRepository,
)
from agentforge.platform.modules.expense.infrastructure.memory_invoice_gate_alert_repository import (  # noqa: E501
    MemoryExpenseInvoiceGateAlertRepository,
)
from agentforge.platform.modules.expense.infrastructure.memory_invoice_repository import (
    MemoryExpenseInvoiceRepository,
)
from agentforge.platform.modules.expense.infrastructure.memory_ocr_job_repository import (
    MemoryExpenseOcrJobRepository,
)
from agentforge.platform.modules.expense.infrastructure.memory_repository import (
    MemoryExpenseClaimRepository,
)
from agentforge.platform.modules.expense.infrastructure.memory_writeback_job_repository import (
    MemoryExpenseWritebackJobRepository,
)
from agentforge.platform.modules.expense.infrastructure.sqlalchemy_attachment_repository import (
    SQLAlchemyExpenseAttachmentRepository,
)
from agentforge.platform.modules.expense.infrastructure.sqlalchemy_extraction_repository import (
    SQLAlchemyExpenseExtractionRepository,
)
from agentforge.platform.modules.expense.infrastructure.sqlalchemy_import_batch_repository import (
    SQLAlchemyExpenseImportBatchRepository,
)
from agentforge.platform.modules.expense.infrastructure.sqlalchemy_invoice_gate_alert_repository import (  # noqa: E501
    SQLAlchemyExpenseInvoiceGateAlertRepository,
)
from agentforge.platform.modules.expense.infrastructure.sqlalchemy_invoice_repository import (
    SQLAlchemyExpenseInvoiceRepository,
)
from agentforge.platform.modules.expense.infrastructure.sqlalchemy_ocr_job_repository import (
    SQLAlchemyExpenseOcrJobRepository,
)
from agentforge.platform.modules.expense.infrastructure.sqlalchemy_repository import (
    SQLAlchemyExpenseClaimRepository,
)
from agentforge.platform.modules.expense.infrastructure.sqlalchemy_writeback_job_repository import (
    SQLAlchemyExpenseWritebackJobRepository,
)
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
from agentforge.platform.modules.support.infrastructure.memory_notification_gateway import (
    MemoryNotificationGateway,
)
from agentforge.platform.modules.support.infrastructure.memory_repository import (
    MemoryTicketRepository,
)
from agentforge.platform.modules.support.infrastructure.sqlalchemy_repository import (
    SQLAlchemyTicketRepository,
)
from agentforge.platform.modules.support.infrastructure.webhook_notification_gateway import (
    WebhookNotificationGateway,
)
from agentforge.platform.modules.support.ports import (
    NotificationPort,
    ReplyConnectorPort,
    TicketRepository,
)
from agentforge.platform.runtime import ServiceContainer
from agentforge.platform.sdk.module import BusinessModule, ModuleConfig, ModuleManifest
from agentforge.platform.settings import Settings


@dataclass(frozen=True)
class ModuleAssemblyContext:
    """模块上下文相关组件。

    Attributes:
        container: 容器。
        enabled_modules: 启用模块。
        session_factory: 会话工厂。
        support_ticket_repository: 客服工单仓储。
        support_reply_connector: 客服回复连接器。
        support_notification_gateway: 客服通知网关。
        expense_claim_repository: 报销报销单仓储。
        support_webhook_secret: 客服Webhook密钥。
    """

    container: ServiceContainer
    enabled_modules: tuple[str, ...] = ("support", "expense")
    session_factory: async_sessionmaker[AsyncSession] | None = None
    support_ticket_repository: TicketRepository | None = None
    support_reply_connector: ReplyConnectorPort | None = None
    support_notification_gateway: NotificationPort | None = None
    expense_claim_repository: ExpenseClaimRepository | None = None
    support_webhook_secret: str = ""


def build_builtin_modules(assembly: ModuleAssemblyContext) -> list[BusinessModule]:
    """构建内置模块。

    Args:
        assembly: 输入参数。

    Returns:
        结果列表。

    Raises:
        ValueError: 输入值或业务状态不合法时抛出。
    """
    known = set(BUILTIN_MODULE_NAMES)
    unknown = sorted(set(assembly.enabled_modules) - known)
    if unknown:
        raise ValueError(f"unknown enabled modules: {', '.join(unknown)}")

    modules: list[BusinessModule] = []
    enabled = set(assembly.enabled_modules)
    if "support" in enabled:
        ticket_repository = assembly.support_ticket_repository
        if ticket_repository is None:
            support_sessions = _module_session_factory(assembly, "support")
            ticket_repository = cast(
                TicketRepository,
                (
                    SQLAlchemyTicketRepository(support_sessions)
                    if support_sessions is not None
                    else MemoryTicketRepository()
                ),
            )
        reply_connector = assembly.support_reply_connector
        if reply_connector is None and assembly.session_factory is None:
            reply_connector = MemoryReplyConnector()
        notification_gateway = assembly.support_notification_gateway or MemoryNotificationGateway()
        modules.append(
            build_support_module(
                assembly.container,
                ticket_repository=ticket_repository,
                reply_connector=reply_connector,
                notification_gateway=notification_gateway,
                webhook_secret=assembly.support_webhook_secret,
            )
        )
    if "expense" in enabled:
        claim_repository = assembly.expense_claim_repository
        expense_sessions = _module_session_factory(assembly, "expense")
        if claim_repository is None:
            claim_repository = cast(
                ExpenseClaimRepository,
                (
                    SQLAlchemyExpenseClaimRepository(expense_sessions)
                    if expense_sessions is not None
                    else MemoryExpenseClaimRepository()
                ),
            )
        attachment_repository = cast(
            ExpenseAttachmentRepository,
            (
                SQLAlchemyExpenseAttachmentRepository(expense_sessions)
                if expense_sessions is not None
                else MemoryExpenseAttachmentRepository()
            ),
        )
        extraction_repository = cast(
            ExpenseExtractionRepository,
            (
                SQLAlchemyExpenseExtractionRepository(expense_sessions)
                if expense_sessions is not None
                else MemoryExpenseExtractionRepository()
            ),
        )
        ocr_job_repository = cast(
            ExpenseOcrJobRepository,
            (
                SQLAlchemyExpenseOcrJobRepository(expense_sessions)
                if expense_sessions is not None
                else MemoryExpenseOcrJobRepository()
            ),
        )
        import_batch_repository = cast(
            ExpenseImportBatchRepository,
            (
                SQLAlchemyExpenseImportBatchRepository(expense_sessions)
                if expense_sessions is not None
                else MemoryExpenseImportBatchRepository()
            ),
        )
        writeback_job_repository = cast(
            ExpenseWritebackJobRepository,
            (
                SQLAlchemyExpenseWritebackJobRepository(expense_sessions)
                if expense_sessions is not None
                else MemoryExpenseWritebackJobRepository()
            ),
        )
        invoice_repository = cast(
            ExpenseInvoiceRepository,
            (
                SQLAlchemyExpenseInvoiceRepository(expense_sessions)
                if expense_sessions is not None
                else MemoryExpenseInvoiceRepository()
            ),
        )
        invoice_gate_alert_repository = cast(
            ExpenseInvoiceGateAlertRepository,
            (
                SQLAlchemyExpenseInvoiceGateAlertRepository(expense_sessions)
                if expense_sessions is not None
                else MemoryExpenseInvoiceGateAlertRepository()
            ),
        )
        modules.append(
            build_expense_module(
                assembly.container,
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
    return modules


BUILTIN_MODULE_NAMES: tuple[str, ...] = ("support", "expense")


def _module_session_factory(
    assembly: ModuleAssemblyContext, module_name: str
) -> async_sessionmaker[AsyncSession] | None:
    """处理模块会话工厂。

    Args:
        assembly: 输入参数。
        module_name: 模块名称。

    Returns:
        处理结果。
    """
    persistence = assembly.container.persistence
    if persistence is not None:
        return persistence.session_factory_for(module_name)
    return assembly.session_factory


def build_module_config(manifest: ModuleManifest, settings: Settings) -> ModuleConfig:
    """构建模块配置。

    Args:
        manifest: 模块或资源清单。
        settings: 应用配置。

    Returns:
        模块配置结果。
    """
    if manifest.name == "support":
        return ModuleConfig(
            values={
                "default_sla_minutes": settings.support_default_sla_minutes,
                "sla_due_soon_seconds": settings.support_sla_due_soon_seconds,
                "invoice_gate_team": settings.support_invoice_gate_team,
                "invoice_gate_assignee": settings.support_invoice_gate_assignee,
                "sla_sweep_minutes": settings.support_sla_sweep_minutes,
                "sla_escalation_assignee": settings.support_sla_escalation_assignee,
                "notification_target": settings.support_notification_target,
                "invoice_gate_sla_minutes": settings.support_invoice_gate_sla_minutes,
            }
        )
    if manifest.name == "expense":
        return ModuleConfig(
            values={
                "category_limits": settings.expense_category_limits,
                "monthly_budget_cents": settings.expense_monthly_budget_cents,
                "invoice_enforcement": settings.expense_invoice_enforcement,
                "invoice_block_alert_hours": settings.expense_invoice_block_alert_hours,
                "invoice_override_alert_count": settings.expense_invoice_override_alert_count,
                "invoice_alert_sweep_minutes": settings.expense_invoice_alert_sweep_minutes,
                "attachment_download_ttl_seconds": settings.attachment_download_ttl_seconds,
            }
        )
    return ModuleConfig()


def build_support_notification_gateway(settings: Settings) -> NotificationPort:
    """构建客服通知网关。

    Args:
        settings: 应用配置。

    Returns:
        通知结果。
    """
    if settings.support_notification_webhook_url:
        return WebhookNotificationGateway(
            settings.support_notification_webhook_url,
            token=settings.support_notification_webhook_token,
            timeout_seconds=settings.support_notification_timeout_seconds,
        )
    return MemoryNotificationGateway()
