"""OCR提取服务模块。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Iterable
from uuid import uuid4

from agentforge.platform.domain.ocr import OcrField
from agentforge.platform.domain.usage import UsageMetric
from agentforge.platform.modules.expense.application.invoice_service import ExpenseInvoiceService
from agentforge.platform.modules.expense.domain.extraction import (
    ExpenseExtraction,
    ExpenseExtractionRecord,
)
from agentforge.platform.modules.expense.ports import ExpenseExtractionRepository
from agentforge.platform.sdk.ports import OcrPort, UsagePort

if TYPE_CHECKING:
    from agentforge.platform.modules.expense.application.service import ExpenseClaimService
    from agentforge.platform.modules.expense.domain.claim import ExpenseClaim

_FIELD_ALIASES = {
    "amount_cents": ("amount_cents", "amount", "total", "金额", "价税合计"),
    "currency": ("currency", "币种"),
    "expense_date": ("expense_date", "date", "日期"),
    "invoice_date": ("invoice_date", "开票日期"),
    "applicant_id": ("applicant_id", "applicant", "employee", "申请人", "报销人"),
    "category": ("category", "type", "类别", "费用类型"),
    "description": ("description", "remark", "说明", "备注"),
    "invoice_code": ("invoice_code", "发票代码"),
    "invoice_number": ("invoice_number", "invoice_no", "发票号码"),
    "seller_tax_id": ("seller_tax_id", "seller_tax_no", "销方税号"),
    "buyer_tax_id": ("buyer_tax_id", "buyer_tax_no", "购方税号"),
}


class ExpenseOcrService:
    """报销OCR应用服务，编排领域用例及其副作用。"""

    def __init__(
        self,
        ocr: OcrPort,
        repository: ExpenseExtractionRepository,
        invoices: ExpenseInvoiceService,
        usage: UsagePort | None = None,
    ) -> None:
        """初始化 ExpenseOcrService。

        Args:
            ocr: OCR。
            repository: 数据仓储实现。
            invoices: 发票。
            usage: 用量统计数据。
        """
        self._ocr = ocr
        self._repository = repository
        self._invoices = invoices
        self._usage = usage

    async def extract(
        self,
        tenant_id: str,
        content: bytes,
        content_type: str = "",
        attachment_id: str | None = None,
    ) -> ExpenseExtraction:
        """提取报销OCR。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            content: 写入内容。
            content_type: 内容 MIME 类型。
            attachment_id: 附件 ID。

        Returns:
            报销提取结果。
        """
        result = await self._ocr.extract(content, content_type)
        fields = {field.name.strip().lower(): field for field in result.fields}
        confidence = {field.name: field.confidence for field in result.fields}
        amount = self._find(fields, _FIELD_ALIASES["amount_cents"])
        expense_date = self._find(fields, _FIELD_ALIASES["expense_date"])
        invoice_date = self._find(fields, _FIELD_ALIASES["invoice_date"])
        currency_field = self._find(fields, _FIELD_ALIASES["currency"])
        extraction_id = str(uuid4())
        extraction = ExpenseExtraction(
            extraction_id=extraction_id,
            attachment_id=attachment_id,
            amount_cents=self._parse_amount(amount.value) if amount else None,
            currency=(currency_field.value or "CNY").upper() if currency_field else "CNY",
            expense_date=(
                self._parse_date(expense_date.value)
                if expense_date
                else self._parse_date(invoice_date.value) if invoice_date else None
            ),
            invoice_date=self._parse_date(invoice_date.value) if invoice_date else None,
            invoice_code=self._value(self._find(fields, _FIELD_ALIASES["invoice_code"])) or "",
            invoice_number=self._value(self._find(fields, _FIELD_ALIASES["invoice_number"])) or "",
            seller_tax_id=self._value(self._find(fields, _FIELD_ALIASES["seller_tax_id"])) or "",
            buyer_tax_id=self._value(self._find(fields, _FIELD_ALIASES["buyer_tax_id"])) or "",
            applicant_id=self._value(self._find(fields, _FIELD_ALIASES["applicant_id"])),
            category=self._value(self._find(fields, _FIELD_ALIASES["category"])),
            description=self._value(self._find(fields, _FIELD_ALIASES["description"])) or "",
            raw_text=result.text,
            provider=result.provider,
            confidence=confidence,
            requires_review=True,
        )
        await self._repository.save(
            ExpenseExtractionRecord(
                extraction_id=extraction_id,
                tenant_id=tenant_id,
                attachment_id=attachment_id,
                extraction=extraction,
                created_at=datetime.now(timezone.utc),
            )
        )
        if self._usage is not None:
            try:
                page_count = max(1, int(result.metadata.get("page_count", 1)))
            except (TypeError, ValueError):
                page_count = 1
            await self._usage.record(
                tenant_id=tenant_id,
                metric=UsageMetric.OCR_PAGES,
                quantity=page_count,
                source=f"expense-ocr:{result.provider or 'unknown'}",
                idempotency_key=f"ocr:{extraction_id}",
                metadata={"attachment_id": attachment_id},
            )
        return extraction

    @staticmethod
    def _find(fields: dict[str, OcrField], aliases: Iterable[str]) -> OcrField | None:
        """查找指定记录。

        Args:
            fields: 字段。
            aliases: 输入参数。

        Returns:
            OCR字段无结果。
        """
        for alias in aliases:
            field = fields.get(alias.lower())
            if field is not None:
                return field
        return None

    @staticmethod
    def _value(field: OcrField | None) -> str | None:
        """提取字段值。

        Args:
            field: 字段。

        Returns:
            无结果。
        """
        if field is None:
            return None
        value = field.value.strip()
        return value or None

    @staticmethod
    def _parse_amount(value: str) -> int:
        """解析金额。

        Args:
            value: 待处理值。

        Returns:
            整数结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        normalized = (
            value.replace(",", "")
            .replace("，", "")
            .replace("¥", "")
            .replace("￥", "")
            .replace("CNY", "")
            .strip()
        )
        try:
            amount = Decimal(normalized)
        except InvalidOperation as exc:
            raise ValueError("OCR amount is not a valid decimal") from exc
        if amount < 0:
            raise ValueError("OCR amount must not be negative")
        return int((amount * 100).quantize(Decimal("1")))

    @staticmethod
    def _parse_date(value: str) -> date:
        """解析报销OCR。

        Args:
            value: 待处理值。

        Returns:
            处理结果对象。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        normalized = (
            value.strip().replace("/", "-").replace("年", "-").replace("月", "-").replace("日", "")
        )
        try:
            return date.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("OCR date must be YYYY-MM-DD") from exc

    async def confirm(
        self,
        *,
        tenant_id: str,
        extraction_id: str,
        body: dict[str, Any],
        claim_service: "ExpenseClaimService",
    ) -> "ExpenseClaim":
        """确认报销OCR。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            extraction_id: 提取 ID。
            body: 请求体数据。
            claim_service: 报销单服务。

        Returns:
            处理结果对象。

        Raises:
            LookupError: 操作无法完成时抛出。
            ValueError: 输入值或业务状态不合法时抛出。
        """
        record = await self._repository.get(tenant_id, extraction_id)
        if record is None:
            raise LookupError("OCR extraction not found")
        if record.consumed_at is not None:
            raise ValueError("OCR extraction has already been confirmed")
        confirmed = body.get("confirmed_fields", {})
        if not isinstance(confirmed, dict):
            raise ValueError("confirmed_fields must be an object")
        allowed = {
            "amount_cents",
            "currency",
            "expense_date",
            "applicant_id",
            "category",
            "description",
            "invoice_date",
            "invoice_code",
            "invoice_number",
            "seller_tax_id",
            "buyer_tax_id",
        }
        unknown = sorted(set(confirmed) - allowed)
        if unknown:
            raise ValueError(f"unsupported confirmed fields: {', '.join(unknown)}")
        fields = record.extraction.model_dump(mode="json")
        fields.update(confirmed)
        claim_body: dict[str, Any] = {
            "tenant_id": tenant_id,
            "idempotency_key": str(body.get("idempotency_key") or f"ocr-{record.extraction_id}"),
            "amount_cents": fields.get("amount_cents"),
            "currency": fields.get("currency") or "CNY",
            "expense_date": fields.get("expense_date"),
            "applicant_id": fields.get("applicant_id"),
            "category": fields.get("category"),
            "description": fields.get("description") or "",
            "metadata": {
                "ocr": {
                    "extraction_id": record.extraction_id,
                    "attachment_id": record.attachment_id,
                    "provider": record.extraction.provider,
                    "confidence": record.extraction.confidence,
                    "raw_text": record.extraction.raw_text,
                    "requires_review": True,
                    "confirmed_fields": confirmed,
                }
            },
        }
        if record.attachment_id is not None:
            claim_body["attachment_ids"] = [record.attachment_id]
        claim = await claim_service.create_claim(claim_body)
        registration = await self._register_invoice_candidate(
            claim,
            fields,
            actor_id=str(body.get("actor_id") or "ocr-confirm"),
        )
        claim = await claim_service.update_claim_metadata(
            tenant_id,
            claim.claim_id,
            {"invoice_registration": registration},
        )
        record.consumed_at = datetime.now(timezone.utc)
        await self._repository.save(record)
        return claim

    async def _register_invoice_candidate(
        self,
        claim: "ExpenseClaim",
        fields: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        """注册发票候选结果。

        Args:
            claim: 报销单对象。
            fields: 字段。
            actor_id: 执行操作的参与者 ID。

        Returns:
            结构化结果字典。
        """
        invoice_number = str(fields.get("invoice_number") or "").strip()
        if not invoice_number:
            return {"status": "skipped", "reason": "invoice_number_missing"}
        payload = {
            "invoice_code": fields.get("invoice_code") or "",
            "invoice_number": invoice_number,
            "invoice_date": fields.get("invoice_date") or fields.get("expense_date"),
            "amount_cents": fields.get("amount_cents"),
            "currency": fields.get("currency") or "CNY",
            "seller_tax_id": fields.get("seller_tax_id") or "",
            "buyer_tax_id": fields.get("buyer_tax_id") or "",
            "metadata": {
                "source": "ocr",
                "extraction_id": fields.get("extraction_id"),
            },
        }
        try:
            invoices = await self._invoices.register_for_claim(
                claim.tenant_id,
                claim.claim_id,
                [payload],
                actor_id=actor_id,
                enforce_authorization=False,
            )
        except Exception as exc:  # noqa: BLE001 - claim remains reviewable on duplicate
            return {"status": "failed", "reason": str(exc)[:500]}
        return {
            "status": "registered",
            "invoice_ids": [invoice.invoice_id for invoice in invoices],
        }
