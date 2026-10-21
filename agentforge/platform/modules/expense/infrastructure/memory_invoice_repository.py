"""记忆发票仓储模块。"""

from __future__ import annotations

from copy import deepcopy

from agentforge.platform.modules.expense.domain.invoice import ExpenseInvoice, ExpenseInvoiceStatus


class MemoryExpenseInvoiceRepository:
    """报销发票仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryExpenseInvoiceRepository。"""
        self._invoices: dict[str, ExpenseInvoice] = {}

    async def save(self, invoice: ExpenseInvoice) -> None:
        """保存报销发票。

        Args:
            invoice: 发票对象。
        """
        self._invoices[invoice.invoice_id] = deepcopy(invoice)

    async def get(self, tenant_id: str, invoice_id: str) -> ExpenseInvoice | None:
        """读取报销发票。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            invoice_id: 发票 ID。

        Returns:
            报销发票无结果。
        """
        invoice = self._invoices.get(invoice_id)
        if invoice is None or invoice.tenant_id != tenant_id:
            return None
        return deepcopy(invoice)

    async def get_active_by_fingerprint(
        self,
        tenant_id: str,
        fingerprint: str,
    ) -> ExpenseInvoice | None:
        """获取活跃由指纹。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            fingerprint: 指纹。

        Returns:
            报销发票无结果。
        """
        for invoice in self._invoices.values():
            if (
                invoice.tenant_id == tenant_id
                and invoice.fingerprint == fingerprint
                and invoice.status == ExpenseInvoiceStatus.ACTIVE
                and invoice.duplicate_key is not None
            ):
                return deepcopy(invoice)
        return None

    async def list_by_claim(self, tenant_id: str, claim_id: str) -> list[ExpenseInvoice]:
        """查询由报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim_id: 报销单 ID。

        Returns:
            结果列表。
        """
        invoices = [
            invoice
            for invoice in self._invoices.values()
            if invoice.tenant_id == tenant_id and invoice.claim_id == claim_id
        ]
        invoices.sort(key=lambda invoice: (invoice.created_at, invoice.invoice_id))
        return [deepcopy(invoice) for invoice in invoices]

    async def list(self, tenant_id: str, limit: int = 200) -> list[ExpenseInvoice]:
        """查询报销发票。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        invoices = [
            invoice for invoice in self._invoices.values() if invoice.tenant_id == tenant_id
        ]
        invoices.sort(key=lambda invoice: (invoice.created_at, invoice.invoice_id), reverse=True)
        return [deepcopy(invoice) for invoice in invoices[:limit]]
