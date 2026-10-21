"""台账服务模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.authorization import AuthorizationOutcome
from agentforge.platform.domain.connector import ConnectorContext
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.risk import RiskLevel
from agentforge.platform.modules.expense.domain.claim import ExpenseClaim, ExpenseClaimStatus
from agentforge.platform.modules.expense.domain.ledger import (
    ExpenseCompensationBatch,
    ExpenseCompensationItem,
    ExpenseCompensationStatus,
    ExpenseLedgerReconciliation,
    ExpenseReconciliationIssue,
    ExpenseVerificationBatch,
    ExpenseVerificationItem,
    ExpenseVerificationStatus,
    ExpenseWritebackBatch,
    ExpenseWritebackItem,
    ExpenseWritebackStatus,
)
from agentforge.platform.modules.expense.ports import ExpenseClaimRepository
from agentforge.platform.sdk.ports import (
    AuditPort,
    AuthorizationPort,
    ConnectorCatalogPort,
    OutboxPort,
)

MAX_LEDGER_CLAIMS = 10_000
MAX_WRITEBACK_CLAIMS = 200


class ExpenseLedgerService:
    """报销台账应用服务，编排领域用例及其副作用。"""

    def __init__(
        self,
        repository: ExpenseClaimRepository,
        connectors: ConnectorCatalogPort,
        authorization: AuthorizationPort,
        audit: AuditPort,
        outbox: OutboxPort,
    ) -> None:
        """初始化 ExpenseLedgerService。

        Args:
            repository: 数据仓储实现。
            connectors: 连接器。
            authorization: 输入参数。
            audit: 审计。
            outbox: Outbox。
        """
        self._repository = repository
        self._connectors = connectors
        self._authorization = authorization
        self._audit = audit
        self._outbox = outbox

    async def list_approved(self, tenant_id: str) -> list[ExpenseClaim]:
        """查询已批准。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        claims = await self._repository.list_all(
            tenant_id,
            status=ExpenseClaimStatus.APPROVED,
            limit=MAX_LEDGER_CLAIMS + 1,
        )
        if len(claims) > MAX_LEDGER_CLAIMS:
            raise ValueError("ledger exceeds the 10000-claim export limit")
        return claims

    async def writeback(
        self,
        tenant_id: str,
        *,
        connector_id: str,
        action: str,
        actor_id: str,
        claim_ids: list[str] | None = None,
    ) -> ExpenseWritebackBatch:
        """执行写回。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            actor_id: 执行操作的参与者 ID。
            claim_ids: 报销单 ID 列表。

        Returns:
            报销写回批次结果。
        """
        connector_id, action, actor_id = await self.authorize_writeback(
            tenant_id,
            connector_id=connector_id,
            action=action,
            actor_id=actor_id,
        )
        normalized = await self.resolve_claim_ids(tenant_id, claim_ids)
        items: list[ExpenseWritebackItem] = []
        for claim_id in normalized:
            claim = await self._repository.get(tenant_id, claim_id)
            if claim is None:
                items.append(
                    ExpenseWritebackItem(
                        claim_id=claim_id,
                        status=ExpenseWritebackStatus.FAILED,
                        error="expense claim not found",
                    )
                )
                continue
            item = await self._writeback_claim(
                claim,
                connector_id=connector_id,
                action=action,
                actor_id=actor_id,
            )
            items.append(item)
        return _build_batch(tenant_id, connector_id, action, items)

    async def verify_writebacks(
        self,
        tenant_id: str,
        *,
        connector_id: str,
        action: str,
        lookup_action: str,
        actor_id: str,
        claim_ids: list[str] | None = None,
    ) -> ExpenseVerificationBatch:
        """校验写回。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            lookup_action: 操作。
            actor_id: 执行操作的参与者 ID。
            claim_ids: 报销单 ID 列表。

        Returns:
            报销核验批次结果。
        """
        connector_id, action, lookup_action, actor_id = await self._authorize_ledger_action(
            tenant_id,
            connector_id=connector_id,
            action=action,
            secondary_action=lookup_action,
            actor_id=actor_id,
            permission_action="expense.ledger.verify",
            resource_type="expense_ledger_verification",
        )
        normalized = await self.resolve_claim_ids(tenant_id, claim_ids)
        items: list[ExpenseVerificationItem] = []
        for claim_id in normalized:
            claim = await self._repository.get(tenant_id, claim_id)
            if claim is None:
                items.append(
                    ExpenseVerificationItem(
                        claim_id=claim_id,
                        status=ExpenseVerificationStatus.FAILED,
                        message="expense claim not found",
                    )
                )
                continue
            items.append(
                await self._verify_claim(
                    claim,
                    connector_id=connector_id,
                    action=action,
                    lookup_action=lookup_action,
                    actor_id=actor_id,
                )
            )
        return _build_verification_batch(tenant_id, connector_id, lookup_action, items)

    async def _verify_claim(
        self,
        claim: ExpenseClaim,
        *,
        connector_id: str,
        action: str,
        lookup_action: str,
        actor_id: str,
    ) -> ExpenseVerificationItem:
        """校验报销单。

        Args:
            claim: 报销单对象。
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            lookup_action: 操作。
            actor_id: 执行操作的参与者 ID。

        Returns:
            报销核验条目结果。
        """
        writeback = _writeback_record(claim, connector_id, action)
        if claim.status != ExpenseClaimStatus.APPROVED:
            return ExpenseVerificationItem(
                claim_id=claim.claim_id,
                status=ExpenseVerificationStatus.FAILED,
                message="only approved claims can be verified",
            )
        if writeback is None or writeback.get("status") not in {
            ExpenseWritebackStatus.SUCCEEDED.value,
            ExpenseWritebackStatus.COMPENSATED.value,
        }:
            return ExpenseVerificationItem(
                claim_id=claim.claim_id,
                status=ExpenseVerificationStatus.FAILED,
                message="successful writeback is required before verification",
            )
        expected_external_id = str(writeback.get("external_id") or "")
        if not expected_external_id:
            return ExpenseVerificationItem(
                claim_id=claim.claim_id,
                status=ExpenseVerificationStatus.FAILED,
                message="writeback has no external voucher id",
            )

        checked_at = datetime.now(timezone.utc)
        trace_id = str(claim.metadata.get("trace_id") or uuid4())
        lookup_key = f"expense-verify:{connector_id}:{lookup_action}:{claim.claim_id}"
        external_id = ""
        external_amount: int | None = None
        external_status = ""
        message = ""
        try:
            result = await self._connectors.invoke(
                connector_id,
                lookup_action,
                {
                    "claim_id": claim.claim_id,
                    "expected_external_id": expected_external_id,
                    "expected_amount_cents": claim.amount_cents,
                    "currency": claim.currency,
                    "writeback_action": action,
                    "idempotency_key": lookup_key,
                },
                ConnectorContext(
                    tenant_id=claim.tenant_id,
                    task_id=claim.claim_id,
                    idempotency_key=lookup_key,
                    trace_id=trace_id,
                    actor=actor_id,
                ),
            )
            if not result.ok:
                status = ExpenseVerificationStatus.FAILED
                message = result.error or "external voucher lookup failed"
            else:
                external_id = _external_id(result.data)
                external_status = str(result.data.get("status") or "")
                raw_amount = result.data.get("amount_cents")
                external_amount = int(raw_amount) if raw_amount is not None else None
                found = result.data.get("found")
                if found is False:
                    status = ExpenseVerificationStatus.NOT_FOUND
                    message = "external voucher was not found"
                elif found is not True:
                    status = ExpenseVerificationStatus.MISMATCH
                    message = "lookup response did not confirm voucher existence"
                elif external_id != expected_external_id:
                    status = ExpenseVerificationStatus.MISMATCH
                    message = "external voucher id does not match writeback"
                elif external_amount is not None and external_amount != claim.amount_cents:
                    status = ExpenseVerificationStatus.MISMATCH
                    message = "external voucher amount does not match claim"
                else:
                    status = ExpenseVerificationStatus.VERIFIED
                    message = "external voucher matches writeback"
        except Exception as exc:  # noqa: BLE001 - verification failures stay visible
            status = ExpenseVerificationStatus.FAILED
            message = str(exc)[:1000]

        record = {
            "connector_id": connector_id,
            "action": action,
            "lookup_action": lookup_action,
            "status": status.value,
            "expected_external_id": expected_external_id,
            "external_id": external_id,
            "external_amount_cents": external_amount,
            "external_status": external_status,
            "message": message,
            "actor_id": actor_id,
            "checked_at": checked_at.isoformat(),
        }
        verifications = _verification_records(claim)
        verifications[_writeback_key(connector_id, action)] = record
        claim.metadata = {
            **claim.metadata,
            "writeback_verifications": verifications,
            "last_writeback_verification": record,
        }
        claim.updated_at = checked_at
        await self._repository.save(claim)
        await self._record_ledger_audit(
            claim,
            action=f"expense.ledger.verification_{status.value}",
            actor_id=actor_id,
            risk_level=RiskLevel.MEDIUM,
            payload=record,
        )
        await self._publish_ledger_event(
            claim,
            event_type=f"expense.ledger.verification_{status.value}.v1",
            trace_id=trace_id,
            payload={**record, "claim_id": claim.claim_id, "amount_cents": claim.amount_cents},
        )
        return ExpenseVerificationItem(
            claim_id=claim.claim_id,
            status=status,
            expected_external_id=expected_external_id,
            external_id=external_id,
            external_amount_cents=external_amount,
            message=message,
            checked_at=checked_at,
        )

    async def compensate_writebacks(
        self,
        tenant_id: str,
        *,
        connector_id: str,
        action: str,
        compensation_action: str,
        actor_id: str,
        reason: str,
        claim_ids: list[str] | None = None,
    ) -> ExpenseCompensationBatch:
        """补偿写回。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            compensation_action: 补偿操作。
            actor_id: 执行操作的参与者 ID。
            reason: 变更原因。
            claim_ids: 报销单 ID 列表。

        Returns:
            报销补偿批次结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        connector_id, action, compensation_action, actor_id = await self._authorize_ledger_action(
            tenant_id,
            connector_id=connector_id,
            action=action,
            secondary_action=compensation_action,
            actor_id=actor_id,
            permission_action="expense.ledger.compensate",
            resource_type="expense_ledger_compensation",
        )
        if not reason.strip():
            raise ValueError("reason is required")
        normalized = await self.resolve_claim_ids(tenant_id, claim_ids)
        items: list[ExpenseCompensationItem] = []
        for claim_id in normalized:
            claim = await self._repository.get(tenant_id, claim_id)
            if claim is None:
                items.append(
                    ExpenseCompensationItem(
                        claim_id=claim_id,
                        status=ExpenseCompensationStatus.FAILED,
                        error="expense claim not found",
                    )
                )
                continue
            items.append(
                await self._compensate_claim(
                    claim,
                    connector_id=connector_id,
                    action=action,
                    compensation_action=compensation_action,
                    actor_id=actor_id,
                    reason=reason.strip(),
                )
            )
        return _build_compensation_batch(
            tenant_id,
            connector_id,
            compensation_action,
            items,
        )

    async def _compensate_claim(
        self,
        claim: ExpenseClaim,
        *,
        connector_id: str,
        action: str,
        compensation_action: str,
        actor_id: str,
        reason: str,
    ) -> ExpenseCompensationItem:
        """补偿报销单。

        Args:
            claim: 报销单对象。
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            compensation_action: 补偿操作。
            actor_id: 执行操作的参与者 ID。
            reason: 变更原因。

        Returns:
            报销补偿条目结果。
        """
        if claim.status != ExpenseClaimStatus.APPROVED:
            return ExpenseCompensationItem(
                claim_id=claim.claim_id,
                status=ExpenseCompensationStatus.FAILED,
                error="only approved claims can be compensated",
            )
        writeback = _writeback_record(claim, connector_id, action)
        if writeback is None:
            return ExpenseCompensationItem(
                claim_id=claim.claim_id,
                status=ExpenseCompensationStatus.FAILED,
                error="writeback not found",
            )
        if writeback.get("status") == ExpenseWritebackStatus.COMPENSATED.value:
            return ExpenseCompensationItem(
                claim_id=claim.claim_id,
                status=ExpenseCompensationStatus.SKIPPED,
                external_id=str(writeback.get("external_id") or ""),
                compensation_id=str(writeback.get("compensation_id") or ""),
            )
        if writeback.get("status") != ExpenseWritebackStatus.SUCCEEDED.value:
            return ExpenseCompensationItem(
                claim_id=claim.claim_id,
                status=ExpenseCompensationStatus.FAILED,
                error="only succeeded writebacks can be compensated",
            )
        external_id = str(writeback.get("external_id") or "")
        if not external_id:
            return ExpenseCompensationItem(
                claim_id=claim.claim_id,
                status=ExpenseCompensationStatus.FAILED,
                error="writeback has no external voucher id",
            )

        compensated_at = datetime.now(timezone.utc)
        trace_id = str(claim.metadata.get("trace_id") or uuid4())
        compensation_key = (
            f"expense-compensate:{connector_id}:{compensation_action}:{claim.claim_id}"
        )
        compensation_id = ""
        error = ""
        try:
            result = await self._connectors.compensate(
                connector_id,
                compensation_action,
                {
                    "claim_id": claim.claim_id,
                    "external_id": external_id,
                    "amount_cents": claim.amount_cents,
                    "currency": claim.currency,
                    "original_action": action,
                    "reason": reason,
                    "idempotency_key": compensation_key,
                },
                ConnectorContext(
                    tenant_id=claim.tenant_id,
                    task_id=claim.claim_id,
                    idempotency_key=compensation_key,
                    trace_id=trace_id,
                    actor=actor_id,
                ),
            )
            ok = result.ok
            compensation_id = _compensation_id(result.data)
            error = result.error or ""
        except Exception as exc:  # noqa: BLE001 - compensation failures remain retryable
            ok = False
            error = str(exc)[:1000]

        status = ExpenseCompensationStatus.SUCCEEDED if ok else ExpenseCompensationStatus.FAILED
        record = {
            "connector_id": connector_id,
            "action": compensation_action,
            "original_action": action,
            "status": status.value,
            "external_id": external_id,
            "compensation_id": compensation_id,
            "reason": reason,
            "error": error,
            "actor_id": actor_id,
            "attempted_at": compensated_at.isoformat(),
            "idempotency_key": compensation_key,
        }
        compensations = _compensation_records(claim)
        compensations[_writeback_key(connector_id, compensation_action)] = record
        metadata = {
            **claim.metadata,
            "compensations": compensations,
            "last_compensation": record,
        }
        if ok:
            writeback = {
                **writeback,
                "status": ExpenseWritebackStatus.COMPENSATED.value,
                "compensated_at": compensated_at.isoformat(),
                "compensation_action": compensation_action,
                "compensation_id": compensation_id,
                "compensation_reason": reason,
            }
            records = _writeback_records(claim)
            records[_writeback_key(connector_id, action)] = writeback
            metadata["writebacks"] = records
            metadata["last_writeback"] = writeback
        claim.metadata = metadata
        claim.updated_at = compensated_at
        await self._repository.save(claim)
        await self._record_ledger_audit(
            claim,
            action=f"expense.ledger.compensation_{status.value}",
            actor_id=actor_id,
            risk_level=RiskLevel.HIGH,
            payload=record,
        )
        await self._publish_ledger_event(
            claim,
            event_type=f"expense.ledger.compensation_{status.value}.v1",
            trace_id=trace_id,
            payload={**record, "claim_id": claim.claim_id, "amount_cents": claim.amount_cents},
        )
        return ExpenseCompensationItem(
            claim_id=claim.claim_id,
            status=status,
            external_id=external_id,
            compensation_id=compensation_id,
            error=error,
            compensated_at=compensated_at,
        )

    async def authorize_writeback(
        self,
        tenant_id: str,
        *,
        connector_id: str,
        action: str,
        actor_id: str,
    ) -> tuple[str, str, str]:
        """授权写回。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            actor_id: 执行操作的参与者 ID。

        Returns:
            结果元组。
        """
        connector_id, action, _, actor_id = await self._authorize_ledger_action(
            tenant_id,
            connector_id=connector_id,
            action=action,
            secondary_action="",
            actor_id=actor_id,
            permission_action="expense.ledger.writeback",
            resource_type="expense_ledger",
        )
        return connector_id, action, actor_id

    async def _authorize_ledger_action(
        self,
        tenant_id: str,
        *,
        connector_id: str,
        action: str,
        secondary_action: str,
        actor_id: str,
        permission_action: str,
        resource_type: str,
    ) -> tuple[str, str, str, str]:
        """授权台账操作。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            secondary_action: 操作。
            actor_id: 执行操作的参与者 ID。
            permission_action: 权限操作。
            resource_type: 资源类型。

        Returns:
            结果元组。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
            PermissionError: 调用方缺少所需权限时抛出。
        """
        connector_id = connector_id.strip()
        action = action.strip()
        secondary_action = secondary_action.strip()
        actor_id = actor_id.strip()
        if not connector_id or not actor_id:
            raise ValueError("connector_id and actor_id are required")
        if permission_action == "expense.ledger.verify" and (not action or not secondary_action):
            raise ValueError("action and lookup_action are required")
        if permission_action == "expense.ledger.compensate" and (
            not action or not secondary_action
        ):
            raise ValueError("action and compensation_action are required")
        if permission_action == "expense.ledger.writeback" and not action:
            raise ValueError("action is required")
        authorization = await self._authorization.authorize(
            tenant_id=tenant_id,
            principal=actor_id,
            action=permission_action,
            resource_type=resource_type,
            resource_id=connector_id,
        )
        if authorization.outcome != AuthorizationOutcome.ALLOWED:
            raise PermissionError("; ".join(authorization.reasons))
        return connector_id, action, secondary_action, actor_id

    async def resolve_claim_ids(
        self,
        tenant_id: str,
        claim_ids: list[str] | None,
        *,
        max_claims: int = MAX_WRITEBACK_CLAIMS,
    ) -> list[str]:
        """解析报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim_ids: 报销单 ID 列表。
            max_claims: 最大报销单。

        Returns:
            结果列表。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if claim_ids is None:
            claims = await self.list_approved(tenant_id)
            if len(claims) > max_claims:
                raise ValueError(f"writeback supports at most {max_claims} claims")
            claim_ids = [claim.claim_id for claim in claims]
            if not claim_ids:
                raise ValueError("no approved claims to write back")
            return claim_ids
        normalized = list(dict.fromkeys(claim_ids))
        if not normalized or len(normalized) > max_claims:
            raise ValueError(f"claim_ids must contain between 1 and {max_claims} claims")
        return normalized

    async def reconcile(
        self,
        tenant_id: str,
        connector_id: str | None = None,
    ) -> ExpenseLedgerReconciliation:
        """对账报销台账。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            connector_id: 连接器 ID。

        Returns:
            报销台账对账结果。
        """
        claims = await self.list_approved(tenant_id)
        written_claims = failed_claims = compensated_claims = pending_claims = 0
        written_amount = failed_amount = compensated_amount = pending_amount = 0
        issues: list[ExpenseReconciliationIssue] = []
        for claim in claims:
            record = _selected_writeback(claim, connector_id)
            status = str(record.get("status") or "") if record else ""
            if status == ExpenseWritebackStatus.SUCCEEDED.value:
                written_claims += 1
                written_amount += claim.amount_cents
            elif status == ExpenseWritebackStatus.COMPENSATED.value:
                compensated_claims += 1
                compensated_amount += claim.amount_cents
            elif status == ExpenseWritebackStatus.FAILED.value:
                failed_claims += 1
                failed_amount += claim.amount_cents
                issues.append(
                    ExpenseReconciliationIssue(
                        claim_id=claim.claim_id,
                        amount_cents=claim.amount_cents,
                        status=status,
                        connector_id=str(record.get("connector_id") or ""),
                        error=str(record.get("error") or ""),
                    )
                )
            else:
                pending_claims += 1
                pending_amount += claim.amount_cents
            verification = _selected_verification(claim, connector_id)
            verification_status = str(verification.get("status") or "") if verification else ""
            if verification_status in {
                ExpenseVerificationStatus.NOT_FOUND.value,
                ExpenseVerificationStatus.MISMATCH.value,
                ExpenseVerificationStatus.FAILED.value,
            }:
                issues.append(
                    ExpenseReconciliationIssue(
                        claim_id=claim.claim_id,
                        amount_cents=claim.amount_cents,
                        status=f"verification_{verification_status}",
                        connector_id=str(verification.get("connector_id") or ""),
                        error=str(verification.get("message") or ""),
                    )
                )
        return ExpenseLedgerReconciliation(
            tenant_id=tenant_id,
            total_claims=len(claims),
            total_amount_cents=sum(claim.amount_cents for claim in claims),
            written_claims=written_claims,
            written_amount_cents=written_amount,
            failed_claims=failed_claims,
            failed_amount_cents=failed_amount,
            compensated_claims=compensated_claims,
            compensated_amount_cents=compensated_amount,
            pending_claims=pending_claims,
            pending_amount_cents=pending_amount,
            issues=issues,
        )

    async def _writeback_claim(
        self,
        claim: ExpenseClaim,
        *,
        connector_id: str,
        action: str,
        actor_id: str,
    ) -> ExpenseWritebackItem:
        """执行写回报销单。

        Args:
            claim: 报销单对象。
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            actor_id: 执行操作的参与者 ID。

        Returns:
            报销写回条目结果。
        """
        if claim.status != ExpenseClaimStatus.APPROVED:
            return ExpenseWritebackItem(
                claim_id=claim.claim_id,
                status=ExpenseWritebackStatus.FAILED,
                error="only approved claims can be written back",
            )
        existing = _writeback_record(claim, connector_id, action)
        if existing and existing.get("status") in {
            ExpenseWritebackStatus.SUCCEEDED.value,
            ExpenseWritebackStatus.COMPENSATED.value,
        }:
            return ExpenseWritebackItem(
                claim_id=claim.claim_id,
                status=ExpenseWritebackStatus.SKIPPED,
                external_id=str(existing.get("external_id") or ""),
                idempotent_replay=True,
            )

        idempotency_key = f"expense-writeback:{connector_id}:{action}:{claim.claim_id}"
        trace_id = str(claim.metadata.get("trace_id") or uuid4())
        try:
            result = await self._connectors.invoke(
                connector_id,
                action,
                _connector_payload(claim, idempotency_key),
                ConnectorContext(
                    tenant_id=claim.tenant_id,
                    task_id=claim.claim_id,
                    idempotency_key=idempotency_key,
                    trace_id=trace_id,
                    actor=actor_id,
                ),
            )
            ok = result.ok
            external_id = _external_id(result.data)
            error = result.error or ""
            idempotent_replay = result.idempotent_replay
        except Exception as exc:  # noqa: BLE001 - failed writes remain retryable
            ok = False
            external_id = ""
            error = str(exc)[:1000]
            idempotent_replay = False

        attempted_at = datetime.now(timezone.utc)
        status = ExpenseWritebackStatus.SUCCEEDED if ok else ExpenseWritebackStatus.FAILED
        record = {
            "connector_id": connector_id,
            "action": action,
            "status": status.value,
            "external_id": external_id,
            "error": error,
            "idempotent_replay": idempotent_replay,
            "actor_id": actor_id,
            "attempted_at": attempted_at.isoformat(),
            "idempotency_key": idempotency_key,
        }
        records = _writeback_records(claim)
        records[_writeback_key(connector_id, action)] = record
        claim.metadata = {
            **claim.metadata,
            "writebacks": records,
            "last_writeback": record,
        }
        claim.updated_at = attempted_at
        await self._repository.save(claim)
        await self._record_writeback_audit(claim, record, actor_id)
        await self._publish_writeback(claim, record, trace_id)
        return ExpenseWritebackItem(
            claim_id=claim.claim_id,
            status=status,
            external_id=external_id,
            error=error,
            idempotent_replay=idempotent_replay,
            attempted_at=attempted_at,
        )

    async def _record_ledger_audit(
        self,
        claim: ExpenseClaim,
        *,
        action: str,
        actor_id: str,
        risk_level: RiskLevel,
        payload: dict[str, Any],
    ) -> None:
        """记录台账审计。

        Args:
            claim: 报销单对象。
            action: 待执行动作名称。
            actor_id: 执行操作的参与者 ID。
            risk_level: 风险级别。
            payload: 事件、工作流或请求载荷。
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
                actor_id=actor_id,
                trace_id=str(claim.metadata.get("trace_id") or uuid4()),
                payload=payload,
            )
        )

    async def _publish_ledger_event(
        self,
        claim: ExpenseClaim,
        *,
        event_type: str,
        trace_id: str,
        payload: dict[str, Any],
    ) -> None:
        """发布台账事件。

        Args:
            claim: 报销单对象。
            event_type: 事件类型。
            trace_id: 链路追踪 ID。
            payload: 事件、工作流或请求载荷。
        """
        await self._outbox.enqueue(
            EventEnvelope(
                event_id=str(uuid4()),
                event_type=event_type,
                tenant_id=claim.tenant_id,
                task_id=claim.claim_id,
                trace_id=trace_id,
                producer="expense-ledger-service",
                payload=payload,
            )
        )

    async def _record_writeback_audit(
        self,
        claim: ExpenseClaim,
        record: dict[str, str | bool],
        actor_id: str,
    ) -> None:
        """记录写回审计。

        Args:
            claim: 报销单对象。
            record: 待处理的领域记录。
            actor_id: 执行操作的参与者 ID。
        """
        status = str(record["status"])
        await self._audit.save(
            AuditEvent(
                event_id=str(uuid4()),
                tenant_id=claim.tenant_id,
                action=f"expense.ledger.writeback_{status}",
                resource_type="expense_claim",
                resource_id=claim.claim_id,
                risk_level=RiskLevel.HIGH,
                actor_type="user",
                actor_id=actor_id,
                trace_id=str(claim.metadata.get("trace_id") or uuid4()),
                payload=dict(record),
            )
        )

    async def _publish_writeback(
        self,
        claim: ExpenseClaim,
        record: dict[str, str | bool],
        trace_id: str,
    ) -> None:
        """发布写回。

        Args:
            claim: 报销单对象。
            record: 待处理的领域记录。
            trace_id: 链路追踪 ID。
        """
        status = str(record["status"])
        await self._outbox.enqueue(
            EventEnvelope(
                event_id=str(uuid4()),
                event_type=f"expense.ledger.writeback_{status}.v1",
                tenant_id=claim.tenant_id,
                task_id=claim.claim_id,
                trace_id=trace_id,
                producer="expense-ledger-service",
                payload={
                    "claim_id": claim.claim_id,
                    "amount_cents": claim.amount_cents,
                    "currency": claim.currency,
                    **record,
                },
            )
        )


def _connector_payload(claim: ExpenseClaim, idempotency_key: str) -> dict[str, object]:
    """执行连接器载荷。

    Args:
        claim: 报销单对象。
        idempotency_key: 幂等键，用于避免重复处理。

    Returns:
        结构化结果字典。
    """
    return {
        "idempotency_key": idempotency_key,
        "claim_id": claim.claim_id,
        "tenant_id": claim.tenant_id,
        "applicant_id": claim.applicant_id,
        "amount_cents": claim.amount_cents,
        "currency": claim.currency,
        "expense_date": claim.expense_date.isoformat(),
        "category": claim.category,
        "description": claim.description,
        "invoice_count": claim.invoice_count,
        "approval": claim.metadata.get("approval", {}),
    }


def _external_id(data: dict[str, Any]) -> str:
    """获取外部系统中的业务标识。

    Args:
        data: 待处理数据。

    Returns:
        字符串结果。
    """
    for key in ("external_id", "voucher_id", "document_id", "id"):
        value = data.get(key)
        if value is not None and str(value):
            return str(value)
    return ""


def _compensation_id(data: dict[str, Any]) -> str:
    """处理补偿ID。

    Args:
        data: 待处理数据。

    Returns:
        字符串结果。
    """
    for key in ("compensation_id", "external_id", "document_id", "id"):
        value = data.get(key)
        if value is not None and str(value):
            return str(value)
    return ""


def _writeback_key(connector_id: str, action: str) -> str:
    """执行写回键。

    Args:
        connector_id: 连接器 ID。
        action: 待执行动作名称。

    Returns:
        字符串结果。
    """
    return f"{connector_id}:{action}"


def _writeback_records(claim: ExpenseClaim) -> dict[str, Any]:
    """处理写回记录。

    Args:
        claim: 报销单对象。

    Returns:
        结构化结果字典。
    """
    raw = claim.metadata.get("writebacks")
    return dict(raw) if isinstance(raw, dict) else {}


def _verification_records(claim: ExpenseClaim) -> dict[str, Any]:
    """处理核验记录。

    Args:
        claim: 报销单对象。

    Returns:
        结构化结果字典。
    """
    raw = claim.metadata.get("writeback_verifications")
    return dict(raw) if isinstance(raw, dict) else {}


def _compensation_records(claim: ExpenseClaim) -> dict[str, Any]:
    """提取补偿记录列表。

    Args:
        claim: 报销单对象。

    Returns:
        结构化结果字典。
    """
    raw = claim.metadata.get("compensations")
    return dict(raw) if isinstance(raw, dict) else {}


def _writeback_record(
    claim: ExpenseClaim,
    connector_id: str,
    action: str,
) -> dict[str, Any] | None:
    """执行写回记录。

    Args:
        claim: 报销单对象。
        connector_id: 连接器 ID。
        action: 待执行动作名称。

    Returns:
        结构化结果字典。
    """
    record = _writeback_records(claim).get(_writeback_key(connector_id, action))
    return dict(record) if isinstance(record, dict) else None


def _selected_writeback(
    claim: ExpenseClaim,
    connector_id: str | None,
) -> dict[str, Any] | None:
    """处理选中写回。

    Args:
        claim: 报销单对象。
        connector_id: 连接器 ID。

    Returns:
        结构化结果字典。
    """
    if connector_id:
        records = _writeback_records(claim)
        matches = [
            dict(record)
            for key, record in records.items()
            if key.startswith(f"{connector_id}:") and isinstance(record, dict)
        ]
        if not matches:
            return None
        return max(matches, key=lambda record: str(record.get("attempted_at") or ""))
    last = claim.metadata.get("last_writeback")
    return dict(last) if isinstance(last, dict) else None


def _selected_verification(
    claim: ExpenseClaim,
    connector_id: str | None,
) -> dict[str, Any] | None:
    """处理选中核验。

    Args:
        claim: 报销单对象。
        connector_id: 连接器 ID。

    Returns:
        结构化结果字典。
    """
    if connector_id:
        records = _verification_records(claim)
        matches = [
            dict(record)
            for key, record in records.items()
            if key.startswith(f"{connector_id}:") and isinstance(record, dict)
        ]
        if not matches:
            return None
        return max(matches, key=lambda record: str(record.get("checked_at") or ""))
    last = claim.metadata.get("last_writeback_verification")
    return dict(last) if isinstance(last, dict) else None


def _build_batch(
    tenant_id: str,
    connector_id: str,
    action: str,
    items: list[ExpenseWritebackItem],
) -> ExpenseWritebackBatch:
    """构建批次。

    Args:
        tenant_id: 租户 ID，用于数据隔离。
        connector_id: 连接器 ID。
        action: 待执行动作名称。
        items: 待处理条目列表。

    Returns:
        报销写回批次结果。
    """
    return ExpenseWritebackBatch(
        tenant_id=tenant_id,
        connector_id=connector_id,
        action=action,
        total=len(items),
        succeeded=sum(item.status == ExpenseWritebackStatus.SUCCEEDED for item in items),
        failed=sum(item.status == ExpenseWritebackStatus.FAILED for item in items),
        skipped=sum(item.status == ExpenseWritebackStatus.SKIPPED for item in items),
        items=items,
    )


def _build_verification_batch(
    tenant_id: str,
    connector_id: str,
    lookup_action: str,
    items: list[ExpenseVerificationItem],
) -> ExpenseVerificationBatch:
    """构建核验批次。

    Args:
        tenant_id: 租户 ID，用于数据隔离。
        connector_id: 连接器 ID。
        lookup_action: 操作。
        items: 待处理条目列表。

    Returns:
        报销核验批次结果。
    """
    return ExpenseVerificationBatch(
        tenant_id=tenant_id,
        connector_id=connector_id,
        lookup_action=lookup_action,
        total=len(items),
        verified=sum(item.status == ExpenseVerificationStatus.VERIFIED for item in items),
        not_found=sum(item.status == ExpenseVerificationStatus.NOT_FOUND for item in items),
        mismatch=sum(item.status == ExpenseVerificationStatus.MISMATCH for item in items),
        failed=sum(item.status == ExpenseVerificationStatus.FAILED for item in items),
        items=items,
    )


def _build_compensation_batch(
    tenant_id: str,
    connector_id: str,
    compensation_action: str,
    items: list[ExpenseCompensationItem],
) -> ExpenseCompensationBatch:
    """构建补偿批次。

    Args:
        tenant_id: 租户 ID，用于数据隔离。
        connector_id: 连接器 ID。
        compensation_action: 补偿操作。
        items: 待处理条目列表。

    Returns:
        报销补偿批次结果。
    """
    return ExpenseCompensationBatch(
        tenant_id=tenant_id,
        connector_id=connector_id,
        compensation_action=compensation_action,
        total=len(items),
        succeeded=sum(item.status == ExpenseCompensationStatus.SUCCEEDED for item in items),
        failed=sum(item.status == ExpenseCompensationStatus.FAILED for item in items),
        skipped=sum(item.status == ExpenseCompensationStatus.SKIPPED for item in items),
        items=items,
    )
