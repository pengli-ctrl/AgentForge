"""记忆仓储模块。"""

from __future__ import annotations

from copy import deepcopy
from datetime import date

from agentforge.platform.modules.expense.domain.claim import ExpenseClaim, ExpenseClaimStatus


class MemoryExpenseClaimRepository:
    """报销单仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryExpenseClaimRepository。"""
        self.claims: dict[str, ExpenseClaim] = {}
        self._idempotency: dict[tuple[str, str], str] = {}

    async def save(self, claim: ExpenseClaim) -> None:
        """保存报销单。

        Args:
            claim: 报销单对象。
        """
        self.claims[claim.claim_id] = deepcopy(claim)
        self._idempotency[(claim.tenant_id, claim.idempotency_key)] = claim.claim_id

    async def get(self, tenant_id: str, claim_id: str) -> ExpenseClaim | None:
        """获取报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim_id: 报销单 ID。

        Returns:
            报销报销单无结果。
        """
        claim = self.claims.get(claim_id)
        if claim is None or claim.tenant_id != tenant_id:
            return None
        return deepcopy(claim)

    async def get_by_idempotency_key(
        self,
        tenant_id: str,
        idempotency_key: str,
    ) -> ExpenseClaim | None:
        """获取由键。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            idempotency_key: 幂等键，用于避免重复处理。

        Returns:
            报销报销单无结果。
        """
        claim_id = self._idempotency.get((tenant_id, idempotency_key))
        return await self.get(tenant_id, claim_id) if claim_id is not None else None

    async def list_page(
        self,
        tenant_id: str,
        *,
        status: ExpenseClaimStatus | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[ExpenseClaim], str | None]:
        """查询页面。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            status: 目标状态。
            limit: 返回记录的最大数量。
            cursor: 分页游标。

        Returns:
            结果元组。
        """
        offset = self._cursor_offset(cursor)
        claims = [
            claim
            for claim in self.claims.values()
            if claim.tenant_id == tenant_id and (status is None or claim.status == status)
        ]
        claims.sort(key=lambda claim: (claim.created_at, claim.claim_id), reverse=True)
        page = claims[offset : offset + limit]
        next_cursor = str(offset + limit) if offset + limit < len(claims) else None
        return [deepcopy(claim) for claim in page], next_cursor

    async def list_all(
        self,
        tenant_id: str,
        *,
        status: ExpenseClaimStatus | None = None,
        limit: int = 10_000,
    ) -> list[ExpenseClaim]:
        """查询全部。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            status: 目标状态。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        claims = [
            claim
            for claim in self.claims.values()
            if claim.tenant_id == tenant_id and (status is None or claim.status == status)
        ]
        claims.sort(key=lambda claim: (claim.created_at, claim.claim_id), reverse=True)
        return [deepcopy(claim) for claim in claims[:limit]]

    async def list_tenants(self) -> list[str]:
        """查询租户。

        Returns:
            结果列表。
        """
        return sorted({claim.tenant_id for claim in self.claims.values()})

    @staticmethod
    def _cursor_offset(cursor: str | None) -> int:
        """解析游标对应的分页偏移量。

        Args:
            cursor: 分页游标。

        Returns:
            整数结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if cursor is None:
            return 0
        try:
            offset = int(cursor)
        except ValueError as exc:
            raise ValueError("invalid cursor") from exc
        if offset < 0:
            raise ValueError("invalid cursor")
        return offset

    async def sum_amount_cents(
        self,
        tenant_id: str,
        statuses: set[ExpenseClaimStatus],
        date_from: date,
        date_to: date,
    ) -> int:
        """汇总报销金额分值。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            statuses: 输入参数。
            date_from: 从。
            date_to: 到。

        Returns:
            整数结果。
        """
        return sum(
            claim.amount_cents
            for claim in self.claims.values()
            if claim.tenant_id == tenant_id
            and claim.status in statuses
            and date_from <= claim.expense_date <= date_to
        )
