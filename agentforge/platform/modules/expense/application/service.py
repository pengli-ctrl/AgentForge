"""服务模块。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.authorization import AuthorizationOutcome
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.knowledge import RetrievedChunk
from agentforge.platform.domain.risk import RiskLevel
from agentforge.platform.modules.expense.application.invoice_service import ExpenseInvoiceService
from agentforge.platform.modules.expense.domain.claim import ExpenseClaim, ExpenseClaimStatus
from agentforge.platform.modules.expense.domain.policy import ExpensePolicy
from agentforge.platform.modules.expense.ports import (
    ExpenseAttachmentRepository,
    ExpenseClaimRepository,
)
from agentforge.platform.sdk.ports import AuditPort, AuthorizationPort, KnowledgePort, OutboxPort


class ExpenseClaimService:
    """报销单应用服务，编排领域用例及其副作用。"""

    def __init__(
        self,
        repository: ExpenseClaimRepository,
        audit: AuditPort,
        outbox: OutboxPort,
        authorization: AuthorizationPort,
        attachment_repository: ExpenseAttachmentRepository,
        policy: ExpensePolicy,
        knowledge: KnowledgePort,
        invoices: ExpenseInvoiceService,
    ) -> None:
        """初始化 ExpenseClaimService。

        Args:
            repository: 数据仓储实现。
            audit: 审计。
            outbox: Outbox。
            authorization: 输入参数。
            attachment_repository: 附件仓储。
            policy: 策略定义。
            knowledge: 知识。
            invoices: 发票。
        """
        self._repository = repository
        self._audit = audit
        self._outbox = outbox
        self._authorization = authorization
        self._attachment_repository = attachment_repository
        self._policy = policy
        self._knowledge = knowledge
        self._invoices = invoices

    async def create_claim(self, body: dict[str, Any]) -> ExpenseClaim:
        """创建报销单。

        Args:
            body: 请求体数据。

        Returns:
            报销报销单结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        tenant_id = self._require_str(body, "tenant_id")
        idempotency_key = self._require_str(body, "idempotency_key")
        existing = await self._repository.get_by_idempotency_key(tenant_id, idempotency_key)
        if existing is not None:
            return existing

        amount_cents = body.get("amount_cents")
        if not isinstance(amount_cents, int) or amount_cents <= 0:
            raise ValueError("amount_cents must be a positive integer")
        invoice_count = body.get("invoice_count", 0)
        if not isinstance(invoice_count, int) or invoice_count < 0:
            raise ValueError("invoice_count must be a non-negative integer")

        expense_date_raw = self._require_str(body, "expense_date")
        try:
            expense_date = date.fromisoformat(expense_date_raw)
        except ValueError as exc:
            raise ValueError("expense_date must use YYYY-MM-DD") from exc

        attachment_ids = self._attachment_ids(body)
        attachments = await self._attachment_repository.list_by_ids(tenant_id, attachment_ids)
        if len(attachments) != len(set(attachment_ids)):
            raise ValueError("one or more attachments were not found for tenant")
        if any(attachment.claim_id is not None for attachment in attachments):
            raise ValueError("one or more attachments are already linked")

        category = self._require_str(body, "category")
        month_start = expense_date.replace(day=1)
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)
        committed = await self._repository.sum_amount_cents(
            tenant_id,
            {
                ExpenseClaimStatus.SUBMITTED,
                ExpenseClaimStatus.WAITING_APPROVAL,
                ExpenseClaimStatus.APPROVED,
            },
            month_start,
            next_month,
        )
        policy_evaluation = self._policy.evaluate(
            amount_cents=amount_cents,
            category=category,
            committed_cents=committed,
        )
        trace_id = self._trace_id(body)
        claim = ExpenseClaim(
            claim_id=str(uuid4()),
            tenant_id=tenant_id,
            applicant_id=self._require_str(body, "applicant_id"),
            amount_cents=amount_cents,
            currency=str(body.get("currency") or "CNY").upper(),
            expense_date=expense_date,
            category=category,
            description=str(body.get("description") or ""),
            invoice_count=invoice_count,
            idempotency_key=idempotency_key,
            metadata={
                **self._metadata(body),
                "trace_id": trace_id,
                "attachment_ids": attachment_ids,
                "policy": policy_evaluation.model_dump(mode="json"),
            },
        )
        await self._repository.save(claim)
        for attachment in attachments:
            attachment.claim_id = claim.claim_id
            await self._attachment_repository.save(attachment)
        await self._record_audit("expense.claim.created", claim)
        await self._publish("expense.claim.created.v1", claim, trace_id)
        return claim

    async def submit_claim(self, tenant_id: str, claim_id: str) -> ExpenseClaim:
        """提交报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim_id: 报销单 ID。

        Returns:
            报销报销单结果。

        Raises:
            LookupError: 操作无法完成时抛出。
        """
        claim = await self._repository.get(tenant_id, claim_id)
        if claim is None:
            raise LookupError("expense claim not found")
        previous_readiness = claim.metadata.get("invoice_readiness")
        readiness = await self._invoices.evaluate_claim(tenant_id, claim)
        readiness_data = readiness.model_dump(mode="json")
        claim.metadata = {
            **claim.metadata,
            "invoice_readiness": readiness_data,
        }
        claim.submit()
        await self._repository.save(claim)
        trace_id = str(claim.metadata.get("trace_id") or uuid4())
        await self._record_audit("expense.claim.submitted", claim)
        await self._publish("expense.claim.submitted.v1", claim, trace_id)
        if previous_readiness != readiness_data and readiness.mode.value != "off":
            await self._emit_readiness_change(claim, previous_readiness, readiness_data, trace_id)
        return claim

    async def get_claim(self, tenant_id: str, claim_id: str) -> ExpenseClaim | None:
        """读取报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim_id: 报销单 ID。

        Returns:
            报销报销单无结果。
        """
        return await self._repository.get(tenant_id, claim_id)

    async def update_claim_metadata(
        self,
        tenant_id: str,
        claim_id: str,
        updates: dict[str, Any],
    ) -> ExpenseClaim:
        """更新报销单元数据。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim_id: 报销单 ID。
            updates: 更新。

        Returns:
            报销报销单结果。

        Raises:
            LookupError: 操作无法完成时抛出。
        """
        claim = await self._repository.get(tenant_id, claim_id)
        if claim is None:
            raise LookupError("expense claim not found")
        claim.metadata = {**claim.metadata, **updates}
        claim.updated_at = datetime.now(timezone.utc)
        await self._repository.save(claim)
        return claim

    async def decide_claim(
        self,
        tenant_id: str,
        claim_id: str,
        *,
        decision: str,
        approver_id: str,
        reason: str = "",
        override_reason: str = "",
    ) -> ExpenseClaim:
        """处理报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim_id: 报销单 ID。
            decision: 待处理的授权或审批决策。
            approver_id: 审批人 ID。
            reason: 变更原因。
            override_reason: 覆盖原因。

        Returns:
            报销报销单结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
            LookupError: 操作无法完成时抛出。
            PermissionError: 调用方缺少所需权限时抛出。
        """
        if decision not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")
        claim = await self._repository.get(tenant_id, claim_id)
        if claim is None:
            raise LookupError("expense claim not found")
        action = f"expense.claim.{decision}"
        authorization = await self._authorization.authorize(
            tenant_id=tenant_id,
            principal=approver_id,
            action=action,
            resource_type="expense_claim",
            resource_id=claim_id,
        )
        if authorization.outcome != AuthorizationOutcome.ALLOWED:
            raise PermissionError("; ".join(authorization.reasons))
        if decision == "approve":
            previous_readiness = claim.metadata.get("invoice_readiness")
            readiness = await self._invoices.evaluate_claim(tenant_id, claim)
            readiness_data = readiness.model_dump(mode="json")
            claim.metadata = {
                **claim.metadata,
                "invoice_readiness": readiness_data,
            }
            trace_id = str(claim.metadata.get("trace_id") or uuid4())
            if previous_readiness != readiness_data and readiness.mode.value != "off":
                await self._emit_readiness_change(
                    claim,
                    previous_readiness,
                    readiness_data,
                    trace_id,
                )
            if not readiness.ready:
                override = await self._authorization.authorize(
                    tenant_id=tenant_id,
                    principal=approver_id,
                    action="expense.invoice.override",
                    resource_type="expense_claim",
                    resource_id=claim_id,
                )
                if override.outcome != AuthorizationOutcome.ALLOWED:
                    await self._record_gate_block(
                        claim,
                        readiness_data,
                        approver_id,
                        "override_permission_denied",
                    )
                    raise PermissionError(
                        "invoice readiness blocked approval: " + ", ".join(readiness.reasons)
                    )
                if not override_reason.strip():
                    await self._record_gate_block(
                        claim,
                        readiness_data,
                        approver_id,
                        "override_reason_missing",
                    )
                    raise ValueError("override_reason is required for invoice gate override")
                await self._record_override_used(
                    claim,
                    readiness_data,
                    approver_id,
                    override_reason.strip(),
                )
            claim.approve(approver_id, reason)
            audit_action = "expense.claim.approved"
            event_type = "expense.claim.approved.v1"
        else:
            claim.reject(approver_id, reason)
            audit_action = "expense.claim.rejected"
            event_type = "expense.claim.rejected.v1"
        await self._repository.save(claim)
        trace_id = str(claim.metadata.get("trace_id") or uuid4())
        await self._record_audit(
            audit_action,
            claim,
            actor_id=approver_id,
            risk_level=RiskLevel.HIGH,
        )
        await self._publish(event_type, claim, trace_id)
        if decision == "approve":
            await self._index_approved_claim(claim)
        else:
            try:
                await self._invoices.release_for_claim(
                    tenant_id,
                    claim_id,
                    actor_id=approver_id,
                    reason=f"claim rejected: {reason}",
                )
                claim = await self._repository.get(tenant_id, claim_id) or claim
            except Exception as exc:  # noqa: BLE001 - rejection remains authoritative
                claim.metadata = {
                    **claim.metadata,
                    "invoice_release": {
                        "status": "failed",
                        "reason": str(exc)[:500],
                    },
                }
                await self._repository.save(claim)
        return claim

    async def index_claim(self, tenant_id: str, claim_id: str) -> ExpenseClaim:
        """建立索引报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim_id: 报销单 ID。

        Returns:
            报销报销单结果。

        Raises:
            LookupError: 操作无法完成时抛出。
            ValueError: 输入值或业务状态不合法时抛出。
        """
        claim = await self._repository.get(tenant_id, claim_id)
        if claim is None:
            raise LookupError("expense claim not found")
        if claim.status != ExpenseClaimStatus.APPROVED:
            raise ValueError("only approved claims can be indexed")
        await self._index_approved_claim(claim)
        return await self._repository.get(tenant_id, claim_id) or claim

    async def search_indexed(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        """搜索报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            query: 检索或筛选查询。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        results = await self._knowledge.search(tenant_id, query, limit=limit * 3)
        filtered = [
            result
            for result in results
            if result.metadata.get("module") == "expense"
            and isinstance(result.metadata.get("claim_id"), str)
        ]
        return filtered[:limit]

    def describe_policy(self) -> dict[str, object]:
        """描述策略。

        Returns:
            结构化结果字典。
        """
        return self._policy.describe()

    async def get_ledger(self, tenant_id: str) -> tuple[list[ExpenseClaim], int]:
        """读取台账。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果元组。
        """
        claims, _ = await self._repository.list_page(
            tenant_id,
            status=ExpenseClaimStatus.APPROVED,
            limit=200,
        )
        return claims, sum(claim.amount_cents for claim in claims)

    async def list_claims(
        self,
        tenant_id: str,
        *,
        status: ExpenseClaimStatus | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[ExpenseClaim], str | None]:
        """查询报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            status: 目标状态。
            limit: 返回记录的最大数量。
            cursor: 分页游标。

        Returns:
            结果元组。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        return await self._repository.list_page(
            tenant_id,
            status=status,
            limit=limit,
            cursor=cursor,
        )

    async def _index_approved_claim(self, claim: ExpenseClaim) -> None:
        """建立索引已批准报销单。

        Args:
            claim: 报销单对象。
        """
        if claim.metadata.get("knowledge_indexed") is True:
            return
        ocr = claim.metadata.get("ocr") if isinstance(claim.metadata.get("ocr"), dict) else {}
        raw_text = str(ocr.get("raw_text") or "")
        content = "\n".join(
            part
            for part in (
                raw_text,
                claim.description,
                f"Category: {claim.category}",
                f"Amount cents: {claim.amount_cents}",
                f"Applicant: {claim.applicant_id}",
            )
            if part
        )
        metadata: dict[str, object] = {
            "module": "expense",
            "claim_id": claim.claim_id,
            "attachment_id": ocr.get("attachment_id"),
            "category": claim.category,
            "amount_cents": claim.amount_cents,
            "applicant_id": claim.applicant_id,
            "expense_date": claim.expense_date.isoformat(),
        }
        try:
            document = await self._knowledge.ingest_document(
                claim.tenant_id,
                title=f"Expense claim {claim.claim_id}",
                content=content,
                source_uri=f"expense://claims/{claim.claim_id}",
                metadata=metadata,
            )
            claim.metadata = {
                **claim.metadata,
                "knowledge_document_id": document.document_id,
                "knowledge_indexed": True,
                "knowledge_index_error": "",
            }
        except Exception as exc:  # noqa: BLE001 - approval must remain recoverable
            claim.metadata = {
                **claim.metadata,
                "knowledge_indexed": False,
                "knowledge_index_error": str(exc)[:500],
            }
            await self._record_audit("expense.claim.index_failed", claim)
        await self._repository.save(claim)

    async def _emit_readiness_change(
        self,
        claim: ExpenseClaim,
        previous: object,
        current: dict[str, Any],
        trace_id: str,
    ) -> None:
        """发送就绪状态。

        Args:
            claim: 报销单对象。
            previous: 上一个。
            current: 输入参数。
            trace_id: 链路追踪 ID。
        """
        payload = {"previous": previous, "current": current}
        await self._audit.save(
            AuditEvent(
                event_id=str(uuid4()),
                tenant_id=claim.tenant_id,
                action="expense.invoice.readiness_changed",
                resource_type="expense_claim",
                resource_id=claim.claim_id,
                risk_level=RiskLevel.MEDIUM,
                actor_type="system",
                actor_id="invoice-gate",
                trace_id=trace_id,
                payload=payload,
            )
        )
        await self._outbox.enqueue(
            EventEnvelope(
                event_id=str(uuid4()),
                event_type="expense.invoice.readiness_changed.v1",
                tenant_id=claim.tenant_id,
                task_id=claim.claim_id,
                trace_id=trace_id,
                producer="expense-claim-service",
                payload={"claim_id": claim.claim_id, **payload},
            )
        )

    async def _record_gate_block(
        self,
        claim: ExpenseClaim,
        readiness: dict[str, Any],
        actor_id: str,
        block_reason: str,
    ) -> None:
        """记录门禁块。

        Args:
            claim: 报销单对象。
            readiness: 就绪状态。
            actor_id: 执行操作的参与者 ID。
            block_reason: 块原因。
        """
        blocked_at = datetime.now(timezone.utc).isoformat()
        existing = claim.metadata.get("invoice_gate_stats")
        stats = dict(existing) if isinstance(existing, dict) else {}
        stats.update(
            {
                "blocked_attempts": int(stats.get("blocked_attempts") or 0) + 1,
                "last_blocked_at": blocked_at,
                "last_block_reason": block_reason,
                "last_blocked_by": actor_id,
                "last_readiness_reasons": readiness.get("reasons", []),
            }
        )
        claim.metadata = {
            **claim.metadata,
            "invoice_readiness": readiness,
            "invoice_gate_stats": stats,
        }
        claim.updated_at = datetime.now(timezone.utc)
        await self._repository.save(claim)
        trace_id = str(claim.metadata.get("trace_id") or uuid4())
        payload = {
            "claim_id": claim.claim_id,
            "block_reason": block_reason,
            "readiness": readiness,
        }
        await self._audit.save(
            AuditEvent(
                event_id=str(uuid4()),
                tenant_id=claim.tenant_id,
                action="expense.invoice.approval_blocked",
                resource_type="expense_claim",
                resource_id=claim.claim_id,
                risk_level=RiskLevel.HIGH,
                actor_type="user",
                actor_id=actor_id,
                trace_id=trace_id,
                payload=payload,
            )
        )
        await self._outbox.enqueue(
            EventEnvelope(
                event_id=str(uuid4()),
                event_type="expense.invoice.approval_blocked.v1",
                tenant_id=claim.tenant_id,
                task_id=claim.claim_id,
                trace_id=trace_id,
                producer="expense-claim-service",
                payload=payload,
            )
        )

    async def _record_override_used(
        self,
        claim: ExpenseClaim,
        readiness: dict[str, Any],
        actor_id: str,
        reason: str,
    ) -> None:
        """记录覆盖已使用。

        Args:
            claim: 报销单对象。
            readiness: 就绪状态。
            actor_id: 执行操作的参与者 ID。
            reason: 变更原因。
        """
        used_at = datetime.now(timezone.utc).isoformat()
        record = {
            "used": True,
            "reason": reason,
            "actor_id": actor_id,
            "used_at": used_at,
            "readiness_reasons": readiness.get("reasons", []),
        }
        claim.metadata = {**claim.metadata, "invoice_override": record}
        trace_id = str(claim.metadata.get("trace_id") or uuid4())
        payload = {"claim_id": claim.claim_id, **record, "readiness": readiness}
        await self._audit.save(
            AuditEvent(
                event_id=str(uuid4()),
                tenant_id=claim.tenant_id,
                action="expense.invoice.override_used",
                resource_type="expense_claim",
                resource_id=claim.claim_id,
                risk_level=RiskLevel.HIGH,
                actor_type="user",
                actor_id=actor_id,
                trace_id=trace_id,
                payload=payload,
            )
        )
        await self._outbox.enqueue(
            EventEnvelope(
                event_id=str(uuid4()),
                event_type="expense.invoice.override_used.v1",
                tenant_id=claim.tenant_id,
                task_id=claim.claim_id,
                trace_id=trace_id,
                producer="expense-claim-service",
                payload=payload,
            )
        )

    async def _record_audit(
        self,
        action: str,
        claim: ExpenseClaim,
        *,
        actor_id: str | None = None,
        risk_level: RiskLevel = RiskLevel.LOW,
    ) -> None:
        """记录审计。

        Args:
            action: 待执行动作名称。
            claim: 报销单对象。
            actor_id: 执行操作的参与者 ID。
            risk_level: 风险级别。
        """
        await self._audit.save(
            AuditEvent(
                event_id=str(uuid4()),
                tenant_id=claim.tenant_id,
                action=action,
                resource_type="expense_claim",
                resource_id=claim.claim_id,
                risk_level=risk_level,
                actor_type="user",
                actor_id=actor_id or claim.applicant_id,
                trace_id=str(claim.metadata.get("trace_id") or uuid4()),
                payload={"status": claim.status.value, "amount_cents": claim.amount_cents},
            )
        )

    async def _publish(
        self,
        event_type: str,
        claim: ExpenseClaim,
        trace_id: str,
    ) -> None:
        """发布报销单。

        Args:
            event_type: 事件类型。
            claim: 报销单对象。
            trace_id: 链路追踪 ID。
        """
        await self._outbox.enqueue(
            EventEnvelope(
                event_id=str(uuid4()),
                event_type=event_type,
                tenant_id=claim.tenant_id,
                task_id=claim.claim_id,
                trace_id=trace_id,
                producer="expense-claim-service",
                payload={
                    "claim_id": claim.claim_id,
                    "status": claim.status.value,
                    "amount_cents": claim.amount_cents,
                    "currency": claim.currency,
                },
            )
        )

    @staticmethod
    def _require_str(body: dict[str, Any], key: str) -> str:
        """处理要求。

        Args:
            body: 请求体数据。
            key: 缓存或配置键。

        Returns:
            字符串结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        value = body.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} is required")
        return value.strip()

    @staticmethod
    def _metadata(body: dict[str, Any]) -> dict[str, Any]:
        """获取记录元数据。

        Args:
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        metadata = body.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        return dict(metadata)

    @staticmethod
    def _attachment_ids(body: dict[str, Any]) -> list[str]:
        """处理附件。

        Args:
            body: 请求体数据。

        Returns:
            结果列表。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        raw = body.get("attachment_ids", [])
        if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
            raise ValueError("attachment_ids must be a list of strings")
        return list(dict.fromkeys(raw))

    @staticmethod
    def _trace_id(body: dict[str, Any]) -> str:
        """处理链路ID。

        Args:
            body: 请求体数据。

        Returns:
            字符串结果。
        """
        value = body.get("trace_id")
        return value if isinstance(value, str) and value else str(uuid4())
