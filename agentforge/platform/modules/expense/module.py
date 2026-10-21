"""模块。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from agentforge.platform.modules.expense.api.router import create_expense_router
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
from agentforge.platform.modules.expense.config import ExpenseModuleConfig, default_expense_config
from agentforge.platform.modules.expense.domain.policy import ExpensePolicy
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
from agentforge.platform.modules.expense.runtime import ExpenseRuntime, configure_expense_runtime
from agentforge.platform.modules.expense.workflows.invoice_gate_sweep import (
    ExpenseInvoiceGateSweepWorkflow,
    sweep_expense_invoice_gate_alerts_activity,
)
from agentforge.platform.modules.expense.workflows.ledger_writeback import (
    ExpenseLedgerWritebackWorkflow,
    process_expense_writeback_job_activity,
)
from agentforge.platform.modules.expense.workflows.ocr_job import (
    ExpenseOcrWorkflow,
    process_expense_ocr_job_activity,
)
from agentforge.platform.sdk.module import ModuleContext, ModuleManifest, ModuleRuntime
from agentforge.platform.sdk.ports import AuthenticatorPort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExpenseModuleDependencies:
    """报销模块依赖相关组件。

    Attributes:
        authenticator: 认证器。
        claim_repository: 报销单仓储。
        attachment_repository: 附件仓储。
        extraction_repository: 提取仓储。
        ocr_job_repository: OCR任务仓储。
        import_batch_repository: 导入批次仓储。
        writeback_job_repository: 写回任务仓储。
        invoice_repository: 发票仓储。
        invoice_gate_alert_repository: 发票门禁告警仓储。
            alert repository。
    """

    authenticator: AuthenticatorPort
    claim_repository: ExpenseClaimRepository
    attachment_repository: ExpenseAttachmentRepository
    extraction_repository: ExpenseExtractionRepository
    ocr_job_repository: ExpenseOcrJobRepository
    import_batch_repository: ExpenseImportBatchRepository
    writeback_job_repository: ExpenseWritebackJobRepository
    invoice_repository: ExpenseInvoiceRepository
    invoice_gate_alert_repository: ExpenseInvoiceGateAlertRepository


class ExpenseModule:
    """报销模块领域组件。"""

    manifest = ModuleManifest(
        name="expense",
        version="0.1.0",
        api_prefix="/v1/expense",
        task_queue="expense-copilot",
        migration_namespace="expense",
        depends_on=(
            "core.tenant",
            "core.audit",
            "core.outbox",
        ),
        enabled_by_default=True,
        config_schema=ExpenseModuleConfig,
        config_defaults=default_expense_config().model_dump(mode="json"),
        permissions=(
            "expense.claim.read",
            "expense.claim.write",
            "expense.claim.approve",
            "expense.ledger.writeback",
            "expense.ledger.verify",
            "expense.ledger.compensate",
            "expense.invoice.read",
            "expense.invoice.write",
            "expense.invoice.verify",
            "expense.invoice.release",
            "expense.invoice.override",
        ),
        published_events=(
            "expense.claim.created.v1",
            "expense.claim.submitted.v1",
            "expense.claim.approved.v1",
            "expense.claim.rejected.v1",
            "expense.ledger.writeback_succeeded.v1",
            "expense.ledger.writeback_failed.v1",
            "expense.ledger.verification_verified.v1",
            "expense.ledger.verification_not_found.v1",
            "expense.ledger.verification_mismatch.v1",
            "expense.ledger.verification_failed.v1",
            "expense.ledger.compensation_succeeded.v1",
            "expense.ledger.compensation_failed.v1",
            "expense.invoice.registered.v1",
            "expense.invoice.verification_verified.v1",
            "expense.invoice.verification_mismatch.v1",
            "expense.invoice.verification_invalid.v1",
            "expense.invoice.verification_failed.v1",
            "expense.invoice.released.v1",
            "expense.invoice.readiness_changed.v1",
            "expense.invoice.approval_blocked.v1",
            "expense.invoice.override_used.v1",
            "expense.invoice.gate_alert.v1",
            "expense.invoice.gate_alert_resolved.v1",
        ),
    )

    def __init__(self, dependencies: ExpenseModuleDependencies) -> None:
        """初始化 ExpenseModule。

        Args:
            dependencies: 依赖。
        """
        self._dependencies = dependencies

    def build(self, ctx: ModuleContext) -> ModuleRuntime:
        """构建报销模块。

        Args:
            ctx: 执行上下文。

        Returns:
            模块运行时结果。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        policy = ExpensePolicy.from_config(dict(ctx.config.values))
        block_alert_value = ctx.config.values.get("invoice_block_alert_hours")
        override_alert_value = ctx.config.values.get("invoice_override_alert_count")
        block_alert_hours = float(str(block_alert_value)) if block_alert_value is not None else 24.0
        override_alert_count = (
            int(str(override_alert_value)) if override_alert_value is not None else 5
        )
        invoice_service = ExpenseInvoiceService(
            self._dependencies.invoice_repository,
            self._dependencies.invoice_gate_alert_repository,
            self._dependencies.claim_repository,
            ctx.connectors,
            ctx.authorization,
            ctx.audit,
            ctx.outbox,
            str(ctx.config.values.get("invoice_enforcement") or "off"),
            block_alert_hours,
            override_alert_count,
        )
        service = ExpenseClaimService(
            self._dependencies.claim_repository,
            ctx.audit,
            ctx.outbox,
            ctx.authorization,
            self._dependencies.attachment_repository,
            policy,
            ctx.knowledge,
            invoice_service,
        )
        attachment_service = ExpenseAttachmentService(
            self._dependencies.attachment_repository,
            ctx.object_store,
            ctx.audit,
            download_url_ttl_seconds=int(
                str(ctx.config.values.get("attachment_download_ttl_seconds") or 300)
            ),
            usage=ctx.usage,
        )
        ocr_service = (
            ExpenseOcrService(
                ctx.ocr,
                self._dependencies.extraction_repository,
                invoice_service,
                usage=ctx.usage,
            )
            if ctx.ocr is not None
            else None
        )
        ocr_job_service = (
            ExpenseOcrJobService(
                self._dependencies.ocr_job_repository,
                attachment_service,
                ocr_service,
                ctx.workflow,
            )
            if ocr_service is not None
            else None
        )
        import_service = ExpenseImportService(
            self._dependencies.import_batch_repository,
            attachment_service,
            ocr_job_service,
        )
        answer_service = ExpenseRagAnswerService(service, ctx.models)
        ledger_service = ExpenseLedgerService(
            self._dependencies.claim_repository,
            ctx.connectors,
            ctx.authorization,
            ctx.audit,
            ctx.outbox,
        )
        writeback_job_service = ExpenseWritebackJobService(
            self._dependencies.writeback_job_repository,
            ledger_service,
            ctx.workflow,
        )
        if ctx.uploads is None:
            raise RuntimeError("resumable upload service is not configured")
        runtime = ExpenseRuntime(
            authenticator=self._dependencies.authenticator,
            module_access=ctx.module_access,
            service=service,
            repository=self._dependencies.claim_repository,
            ocr_service=ocr_service,
            ocr_job_service=ocr_job_service,
            attachment_service=attachment_service,
            import_service=import_service,
            answer_service=answer_service,
            ledger_service=ledger_service,
            writeback_job_service=writeback_job_service,
            invoice_service=invoice_service,
            uploads=ctx.uploads,
        )
        configure_expense_runtime(runtime)
        sweep_value = ctx.config.values.get("invoice_alert_sweep_minutes")
        sweep_minutes = float(str(sweep_value)) if sweep_value is not None else 15.0

        async def ensure_alert_sweep_schedule() -> None:
            """确保告警扫描调度。"""
            if ctx.workflow is None or sweep_minutes <= 0:
                return
            ensure_schedule = getattr(ctx.workflow, "ensure_schedule", None)
            if not callable(ensure_schedule):
                logger.warning(
                    "workflow client cannot ensure invoice alert schedules; "
                    "automatic sweep disabled"
                )
                return
            await ensure_schedule(
                ExpenseInvoiceGateSweepWorkflow,
                {},
                schedule_id="expense-invoice-gate-sweep",
                interval_seconds=sweep_minutes * 60,
                task_queue=self.manifest.task_queue,
                workflow_id="expense-invoice-gate-sweep-run",
            )

        return ModuleRuntime(
            router=create_expense_router(runtime),
            temporal_workflows=[
                ExpenseOcrWorkflow,
                ExpenseLedgerWritebackWorkflow,
                ExpenseInvoiceGateSweepWorkflow,
            ],
            temporal_activities=[
                process_expense_ocr_job_activity,
                process_expense_writeback_job_activity,
                sweep_expense_invoice_gate_alerts_activity,
            ],
            metric_providers=[invoice_service.render_all_gate_metrics],
            startup_hooks=[ensure_alert_sweep_schedule],
        )
