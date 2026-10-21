"""运行时模块。"""

from __future__ import annotations

from dataclasses import dataclass

from agentforge.platform.modules.expense.application.answer_service import ExpenseRagAnswerService
from agentforge.platform.modules.expense.application.attachment_service import (
    ExpenseAttachmentService,
)
from agentforge.platform.modules.expense.application.import_service import ExpenseImportService
from agentforge.platform.modules.expense.application.invoice_service import ExpenseInvoiceService
from agentforge.platform.modules.expense.application.ledger_service import ExpenseLedgerService
from agentforge.platform.modules.expense.application.ocr_extraction_service import ExpenseOcrService
from agentforge.platform.modules.expense.application.ocr_job_service import ExpenseOcrJobService
from agentforge.platform.modules.expense.application.service import ExpenseClaimService
from agentforge.platform.modules.expense.application.writeback_job_service import (
    ExpenseWritebackJobService,
)
from agentforge.platform.modules.expense.ports import ExpenseClaimRepository
from agentforge.platform.sdk.ports import AuthenticatorPort, ChunkedUploadPort, ModuleAccessPort


@dataclass(frozen=True)
class ExpenseRuntime:
    """报销运行时相关组件。

    Attributes:
        authenticator: 认证器。
        module_access: 模块访问。
        service: 服务。
        repository: 数据仓储实现。
        ocr_service: OCR服务。
        ocr_job_service: OCR任务服务。
        attachment_service: 附件服务。
        import_service: 导入服务。
        answer_service: 回答服务。
        ledger_service: 台账服务。
        writeback_job_service: 写回任务服务。
        invoice_service: 发票服务。
        uploads: 上传。
    """

    authenticator: AuthenticatorPort
    module_access: ModuleAccessPort
    service: ExpenseClaimService
    repository: ExpenseClaimRepository
    ocr_service: ExpenseOcrService | None
    ocr_job_service: ExpenseOcrJobService | None
    attachment_service: ExpenseAttachmentService
    import_service: ExpenseImportService
    answer_service: ExpenseRagAnswerService
    ledger_service: ExpenseLedgerService
    writeback_job_service: ExpenseWritebackJobService
    invoice_service: ExpenseInvoiceService
    uploads: ChunkedUploadPort


_expense_runtime: ExpenseRuntime | None = None


def configure_expense_runtime(runtime: ExpenseRuntime) -> None:
    """配置报销运行时。

    Args:
        runtime: 运行时容器。
    """
    global _expense_runtime
    _expense_runtime = runtime


def get_expense_runtime() -> ExpenseRuntime:
    """获取报销运行时。

    Returns:
        报销运行时结果。

    Raises:
        RuntimeError: 运行时依赖或状态不满足要求时抛出。
    """
    if _expense_runtime is None:
        raise RuntimeError("Expense runtime has not been configured")
    return _expense_runtime


def reset_expense_runtime() -> None:
    """重置报销运行时。"""
    global _expense_runtime
    _expense_runtime = None
