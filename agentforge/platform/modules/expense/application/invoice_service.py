"""发票服务模块。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.authorization import AuthorizationOutcome
from agentforge.platform.domain.connector import ConnectorContext
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.risk import RiskLevel
from agentforge.platform.modules.expense.domain.claim import ExpenseClaim, ExpenseClaimStatus
from agentforge.platform.modules.expense.domain.invoice import (
    ExpenseInvoice,
    ExpenseInvoiceEnforcementMode,
    ExpenseInvoiceStatus,
    ExpenseInvoiceVerificationStatus,
    InvoiceDuplicateCheckItem,
    InvoiceDuplicateCheckResult,
    InvoiceDuplicateMatch,
    InvoiceGateAlert,
    InvoiceGateAlertState,
    InvoiceGateSummary,
    InvoiceReadiness,
    InvoiceVerificationResult,
    invoice_fingerprint,
    normalize_invoice_payload,
)
from agentforge.platform.modules.expense.ports import (
    ExpenseClaimRepository,
    ExpenseInvoiceGateAlertRepository,
    ExpenseInvoiceRepository,
)
from agentforge.platform.sdk.ports import (
    AuditPort,
    AuthorizationPort,
    ConnectorCatalogPort,
    OutboxPort,
)


class ExpenseInvoiceService:
    """报销发票应用服务，编排领域用例及其副作用。"""

    def __init__(
        self,
        repository: ExpenseInvoiceRepository,
        alerts: ExpenseInvoiceGateAlertRepository,
        claims: ExpenseClaimRepository,
        connectors: ConnectorCatalogPort,
        authorization: AuthorizationPort,
        audit: AuditPort,
        outbox: OutboxPort,
        enforcement_mode: str = "off",
        block_alert_hours: float = 24.0,
        override_alert_count: int = 5,
    ) -> None:
        """初始化 ExpenseInvoiceService。

        Args:
            repository: 数据仓储实现。
            alerts: 告警。
            claims: 报销单。
            connectors: 连接器。
            authorization: 输入参数。
            audit: 审计。
            outbox: Outbox。
            enforcement_mode: 模式。
            block_alert_hours: 块告警。
            override_alert_count: 覆盖告警数量。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        self._repository = repository
        self._alerts = alerts
        self._claims = claims
        self._connectors = connectors
        self._authorization = authorization
        self._audit = audit
        self._outbox = outbox
        try:
            self._enforcement_mode = ExpenseInvoiceEnforcementMode(enforcement_mode)
        except ValueError as exc:
            raise ValueError(f"unsupported invoice enforcement mode: {enforcement_mode}") from exc
        self._block_alert_hours = max(block_alert_hours, 0.0)
        self._override_alert_count = max(override_alert_count, 1)

    async def check_duplicates(
        self,
        tenant_id: str,
        invoices: list[dict[str, Any]],
    ) -> InvoiceDuplicateCheckResult:
        """检查报销发票。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            invoices: 发票。

        Returns:
            发票重复检查结果结果。
        """
        items: list[InvoiceDuplicateCheckItem] = []
        seen: dict[str, dict[str, Any]] = {}
        for index, payload in enumerate(invoices):
            normalized = normalize_invoice_payload(payload)
            fingerprint = invoice_fingerprint(normalized)
            existing = await self._repository.get_active_by_fingerprint(tenant_id, fingerprint)
            match = _match(existing) if existing is not None else None
            if match is None and fingerprint in seen:
                candidate = seen[fingerprint]
                match = InvoiceDuplicateMatch(
                    invoice_id="",
                    claim_id="",
                    fingerprint=fingerprint,
                    invoice_number=str(candidate["invoice_number"]),
                    amount_cents=int(candidate["amount_cents"]),
                )
            seen.setdefault(fingerprint, normalized)
            items.append(
                InvoiceDuplicateCheckItem(
                    index=index,
                    fingerprint=fingerprint,
                    duplicate=match is not None,
                    match=match,
                )
            )
        return InvoiceDuplicateCheckResult(
            tenant_id=tenant_id,
            duplicates_found=sum(item.duplicate for item in items),
            items=items,
        )

    async def register_for_claim(
        self,
        tenant_id: str,
        claim_id: str,
        invoices: list[dict[str, Any]],
        *,
        actor_id: str,
        enforce_authorization: bool = True,
    ) -> list[ExpenseInvoice]:
        """注册用于报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim_id: 报销单 ID。
            invoices: 发票。
            actor_id: 执行操作的参与者 ID。
            enforce_authorization: 输入参数。

        Returns:
            结果列表。

        Raises:
            LookupError: 操作无法完成时抛出。
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if enforce_authorization:
            await self._authorize(tenant_id, actor_id, "expense.invoice.write", claim_id)
        claim = await self._claims.get(tenant_id, claim_id)
        if claim is None:
            raise LookupError("expense claim not found")
        if claim.status in {ExpenseClaimStatus.REJECTED, ExpenseClaimStatus.ARCHIVED}:
            raise ValueError("cannot register invoices for a closed claim")
        if not invoices:
            raise ValueError("invoices must contain at least one item")

        seen: set[str] = set()
        to_create: list[tuple[dict[str, Any], str]] = []
        for payload in invoices:
            normalized = normalize_invoice_payload(payload)
            fingerprint = invoice_fingerprint(normalized)
            if fingerprint in seen:
                raise ValueError("duplicate invoice exists within request")
            seen.add(fingerprint)
            existing = await self._repository.get_active_by_fingerprint(tenant_id, fingerprint)
            if existing is not None and existing.claim_id != claim_id:
                raise ValueError(f"duplicate invoice already linked to claim {existing.claim_id}")
            if existing is not None:
                continue
            to_create.append((normalized, fingerprint))
        for normalized, fingerprint in to_create:
            invoice = _invoice_from_payload(tenant_id, claim_id, normalized, fingerprint)
            await self._repository.save(invoice)
            await self._record_event(invoice, "expense.invoice.registered.v1", actor_id)

        active = [
            invoice
            for invoice in await self._repository.list_by_claim(tenant_id, claim_id)
            if invoice.status == ExpenseInvoiceStatus.ACTIVE
        ]
        claim.invoice_count = len(active)
        claim.updated_at = datetime.now(timezone.utc)
        await self._claims.save(claim)
        return active

    async def verify_invoice(
        self,
        tenant_id: str,
        invoice_id: str,
        *,
        connector_id: str,
        action: str,
        actor_id: str,
    ) -> InvoiceVerificationResult:
        """校验发票。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            invoice_id: 发票 ID。
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            actor_id: 执行操作的参与者 ID。

        Returns:
            发票核验结果结果。

        Raises:
            LookupError: 操作无法完成时抛出。
            ValueError: 输入值或业务状态不合法时抛出。
        """
        await self._authorize(tenant_id, actor_id, "expense.invoice.verify", invoice_id)
        invoice = await self._repository.get(tenant_id, invoice_id)
        if invoice is None:
            raise LookupError("expense invoice not found")
        if invoice.status != ExpenseInvoiceStatus.ACTIVE:
            raise ValueError("only active invoices can be verified")
        if not connector_id.strip() or not action.strip() or not actor_id.strip():
            raise ValueError("connector_id, action, and actor_id are required")

        verified_at = datetime.now(timezone.utc)
        provider = connector_id
        verification_ref = ""
        message = ""
        idempotency_key = f"expense-invoice-verify:{connector_id}:{invoice.invoice_id}"
        try:
            result = await self._connectors.invoke(
                connector_id,
                action,
                {
                    "invoice_id": invoice.invoice_id,
                    "tenant_id": tenant_id,
                    "claim_id": invoice.claim_id,
                    "invoice_code": invoice.invoice_code,
                    "invoice_number": invoice.invoice_number,
                    "invoice_date": invoice.invoice_date.isoformat(),
                    "amount_cents": invoice.amount_cents,
                    "currency": invoice.currency,
                    "seller_tax_id": invoice.seller_tax_id,
                    "buyer_tax_id": invoice.buyer_tax_id,
                    "idempotency_key": idempotency_key,
                },
                ConnectorContext(
                    tenant_id=tenant_id,
                    task_id=invoice.invoice_id,
                    idempotency_key=idempotency_key,
                    trace_id=str(invoice.metadata.get("trace_id") or uuid4()),
                    actor=actor_id,
                ),
            )
            provider = str(result.data.get("provider") or connector_id)
            verification_ref = _verification_ref(result.data)
            valid = result.data.get("valid")
            if not result.ok:
                status = ExpenseInvoiceVerificationStatus.FAILED
                message = result.error or "invoice verification failed"
            elif valid is False:
                status = ExpenseInvoiceVerificationStatus.INVALID
                message = str(result.data.get("message") or "invoice is invalid")
            elif valid is not True:
                status = ExpenseInvoiceVerificationStatus.FAILED
                message = "verification response did not contain a boolean valid flag"
            elif _verification_mismatch(invoice, result.data):
                status = ExpenseInvoiceVerificationStatus.MISMATCH
                message = "verified invoice fields do not match registry"
            else:
                status = ExpenseInvoiceVerificationStatus.VERIFIED
                message = "invoice verified successfully"
        except Exception as exc:  # noqa: BLE001 - verification failures stay visible
            status = ExpenseInvoiceVerificationStatus.FAILED
            message = str(exc)[:1000]

        invoice.verification_status = status
        invoice.verification_provider = provider
        invoice.verification_ref = verification_ref
        invoice.verification_message = message
        invoice.verified_at = verified_at
        invoice.updated_at = verified_at
        await self._repository.save(invoice)
        await self._record_invoice_audit(
            invoice,
            action=f"expense.invoice.verification_{status.value}",
            actor_id=actor_id,
            risk_level=RiskLevel.MEDIUM,
            payload={
                "status": status.value,
                "provider": provider,
                "verification_ref": verification_ref,
                "message": message,
            },
        )
        await self._publish_event(
            invoice,
            event_type=f"expense.invoice.verification_{status.value}.v1",
            payload={
                "claim_id": invoice.claim_id,
                "status": status.value,
                "provider": provider,
                "verification_ref": verification_ref,
                "message": message,
            },
        )
        return InvoiceVerificationResult(
            invoice_id=invoice.invoice_id,
            claim_id=invoice.claim_id,
            status=status,
            provider=provider,
            verification_ref=verification_ref,
            message=message,
            verified_at=verified_at,
        )

    async def release_invoice(
        self,
        tenant_id: str,
        invoice_id: str,
        *,
        actor_id: str,
        reason: str,
        enforce_authorization: bool = True,
    ) -> ExpenseInvoice:
        """释放发票。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            invoice_id: 发票 ID。
            actor_id: 执行操作的参与者 ID。
            reason: 变更原因。
            enforce_authorization: 输入参数。

        Returns:
            报销发票结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
            LookupError: 操作无法完成时抛出。
        """
        if enforce_authorization:
            await self._authorize(tenant_id, actor_id, "expense.invoice.release", invoice_id)
        if not reason.strip():
            raise ValueError("reason is required")
        invoice = await self._repository.get(tenant_id, invoice_id)
        if invoice is None:
            raise LookupError("expense invoice not found")
        if invoice.status != ExpenseInvoiceStatus.ACTIVE:
            raise ValueError("invoice is already released")
        released_at = datetime.now(timezone.utc)
        invoice.status = ExpenseInvoiceStatus.RELEASED
        invoice.duplicate_key = None
        invoice.release_reason = reason.strip()
        invoice.released_at = released_at
        invoice.updated_at = released_at
        await self._repository.save(invoice)
        claim = await self._claims.get(tenant_id, invoice.claim_id)
        if claim is not None:
            active = [
                item
                for item in await self._repository.list_by_claim(tenant_id, invoice.claim_id)
                if item.status == ExpenseInvoiceStatus.ACTIVE
            ]
            claim.invoice_count = len(active)
            claim.updated_at = released_at
            await self._claims.save(claim)
        await self._record_invoice_audit(
            invoice,
            action="expense.invoice.released",
            actor_id=actor_id,
            risk_level=RiskLevel.MEDIUM,
            payload={"reason": invoice.release_reason},
        )
        await self._publish_event(
            invoice,
            event_type="expense.invoice.released.v1",
            payload={"claim_id": invoice.claim_id, "reason": invoice.release_reason},
        )
        return invoice

    async def release_for_claim(
        self,
        tenant_id: str,
        claim_id: str,
        *,
        actor_id: str,
        reason: str,
    ) -> list[ExpenseInvoice]:
        """处理释放用于报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim_id: 报销单 ID。
            actor_id: 执行操作的参与者 ID。
            reason: 变更原因。

        Returns:
            结果列表。
        """
        active = [
            invoice
            for invoice in await self._repository.list_by_claim(tenant_id, claim_id)
            if invoice.status == ExpenseInvoiceStatus.ACTIVE
        ]
        released: list[ExpenseInvoice] = []
        for invoice in active:
            released.append(
                await self.release_invoice(
                    tenant_id,
                    invoice.invoice_id,
                    actor_id=actor_id,
                    reason=reason,
                    enforce_authorization=False,
                )
            )
        claim = await self._claims.get(tenant_id, claim_id)
        if claim is not None:
            claim.metadata = {
                **claim.metadata,
                "invoice_release": {
                    "status": "released" if released else "no_active_invoices",
                    "count": len(released),
                    "reason": reason,
                    "released_at": datetime.now(timezone.utc).isoformat(),
                },
            }
            claim.updated_at = datetime.now(timezone.utc)
            await self._claims.save(claim)
        return released

    async def list_for_claim(self, tenant_id: str, claim_id: str) -> list[ExpenseInvoice]:
        """查询用于报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim_id: 报销单 ID。

        Returns:
            结果列表。
        """
        return await self._repository.list_by_claim(tenant_id, claim_id)

    async def evaluate_claim(self, tenant_id: str, claim: ExpenseClaim) -> InvoiceReadiness:
        """评估报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            claim: 报销单对象。

        Returns:
            发票就绪状态结果。
        """
        invoices = [
            invoice
            for invoice in await self._repository.list_by_claim(tenant_id, claim.claim_id)
            if invoice.status == ExpenseInvoiceStatus.ACTIVE
        ]
        registration = claim.metadata.get("invoice_registration")
        registration = registration if isinstance(registration, dict) else {}
        registration_status = str(registration.get("status") or "")
        registration_reason = str(registration.get("reason") or "")
        verified = sum(
            invoice.verification_status == ExpenseInvoiceVerificationStatus.VERIFIED
            for invoice in invoices
        )
        total_amount = sum(invoice.amount_cents for invoice in invoices)
        reasons: list[str] = []
        if self._enforcement_mode == ExpenseInvoiceEnforcementMode.DUPLICATE_ONLY:
            if registration_status == "failed" and "duplicate" in registration_reason.lower():
                reasons.append("duplicate_invoice_detected")
        elif self._enforcement_mode in {
            ExpenseInvoiceEnforcementMode.VERIFIED,
            ExpenseInvoiceEnforcementMode.STRICT,
        }:
            if registration_status == "failed":
                reasons.append("invoice_registration_failed")
            if not invoices:
                reasons.append("no_active_invoices")
            for invoice in invoices:
                if invoice.verification_status != ExpenseInvoiceVerificationStatus.VERIFIED:
                    reasons.append(
                        f"invoice_not_verified:{invoice.invoice_id}:"
                        f"{invoice.verification_status.value}"
                    )
            if (
                self._enforcement_mode == ExpenseInvoiceEnforcementMode.STRICT
                and invoices
                and total_amount != claim.amount_cents
            ):
                reasons.append("invoice_amount_mismatch")
        return InvoiceReadiness(
            tenant_id=tenant_id,
            claim_id=claim.claim_id,
            mode=self._enforcement_mode,
            ready=not reasons,
            reasons=reasons,
            active_invoices=len(invoices),
            verified_invoices=verified,
            total_invoice_amount_cents=total_amount,
            registration_status=registration_status,
        )

    async def gate_summary(self, tenant_id: str) -> InvoiceGateSummary:
        """执行门禁摘要。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            发票门禁摘要结果。
        """
        claims = await self._claims.list_all(tenant_id, limit=10_000)
        ready_claims = not_ready_claims = override_claims = blocked_attempts = 0
        reason_counts: dict[str, int] = {}
        last_blocked_at = ""
        oldest_blocked_at = ""
        oldest_blocked_claim_id = ""
        override_actors: dict[str, int] = {}
        claims_with_readiness = 0
        for claim in claims:
            readiness = claim.metadata.get("invoice_readiness")
            if isinstance(readiness, dict):
                claims_with_readiness += 1
                if readiness.get("ready") is True:
                    ready_claims += 1
                else:
                    not_ready_claims += 1
                reasons = readiness.get("reasons")
                if isinstance(reasons, list):
                    for reason in reasons:
                        key = str(reason).split(":", 1)[0]
                        reason_counts[key] = reason_counts.get(key, 0) + 1
            override = claim.metadata.get("invoice_override")
            if isinstance(override, dict) and override.get("used") is True:
                override_claims += 1
                actor = str(override.get("actor_id") or "unknown")
                override_actors[actor] = override_actors.get(actor, 0) + 1
            stats = claim.metadata.get("invoice_gate_stats")
            if isinstance(stats, dict):
                blocked_attempts += int(stats.get("blocked_attempts") or 0)
                blocked_at = str(stats.get("last_blocked_at") or "")
                last_blocked_at = max(last_blocked_at, blocked_at)
                if blocked_at and (not oldest_blocked_at or blocked_at < oldest_blocked_at):
                    oldest_blocked_at = blocked_at
                    oldest_blocked_claim_id = claim.claim_id
        oldest_age = 0.0
        if oldest_blocked_at:
            try:
                oldest_age = max(
                    0.0,
                    (
                        datetime.now(timezone.utc) - datetime.fromisoformat(oldest_blocked_at)
                    ).total_seconds(),
                )
            except ValueError:
                oldest_age = 0.0
        alerts: list[InvoiceGateAlert] = []
        if oldest_blocked_at and oldest_age >= self._block_alert_hours * 3600:
            alerts.append(
                InvoiceGateAlert(
                    type="stale_invoice_gate_block",
                    severity="warning",
                    message=(
                        "an invoice gate block has remained unresolved beyond the "
                        "alert threshold"
                    ),
                    value=oldest_age,
                    claim_id=oldest_blocked_claim_id,
                    anchor=oldest_blocked_at,
                )
            )
        frequent_actor = next(
            (
                (actor, count)
                for actor, count in sorted(override_actors.items(), key=lambda item: -item[1])
                if count >= self._override_alert_count
            ),
            None,
        )
        if frequent_actor is not None:
            alerts.append(
                InvoiceGateAlert(
                    type="frequent_invoice_override",
                    severity="high",
                    message=(
                        f"actor {frequent_actor[0]} used invoice override "
                        f"{frequent_actor[1]} times"
                    ),
                    value=float(frequent_actor[1]),
                    actor_id=frequent_actor[0],
                    anchor=str(frequent_actor[1]),
                )
            )
        return InvoiceGateSummary(
            tenant_id=tenant_id,
            claims_with_readiness=claims_with_readiness,
            ready_claims=ready_claims,
            not_ready_claims=not_ready_claims,
            override_claims=override_claims,
            blocked_attempts=blocked_attempts,
            reason_counts=reason_counts,
            last_blocked_at=last_blocked_at,
            oldest_blocked_at=oldest_blocked_at,
            oldest_blocked_age_seconds=oldest_age,
            override_actors=override_actors,
            alerts=alerts,
        )

    async def emit_gate_alerts(self, tenant_id: str) -> dict[str, Any]:
        """发送门禁告警。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        summary = await self.gate_summary(tenant_id)
        current = {self._gate_alert_key(tenant_id, alert): alert for alert in summary.alerts}
        active = {state.alert_key: state for state in await self._alerts.list_active(tenant_id)}
        now = datetime.now(timezone.utc)
        created = 0
        resolved = 0
        unchanged = 0
        retried = 0
        events: list[dict[str, Any]] = []

        for alert_key, alert in current.items():
            state = active.get(alert_key)
            is_new = state is None
            if state is None:
                occurrence = await self._alerts.count_occurrences(tenant_id, alert_key) + 1
                candidate_alert_id = str(uuid4())
                candidate = InvoiceGateAlertState(
                    alert_id=candidate_alert_id,
                    tenant_id=tenant_id,
                    alert_key=alert_key,
                    type=alert.type,
                    severity=alert.severity,
                    message=alert.message,
                    value=alert.value,
                    claim_id=alert.claim_id,
                    actor_id=alert.actor_id,
                    occurrence=occurrence,
                    created_at=now,
                    updated_at=now,
                )
                await self._alerts.save(candidate)
                state = await self._alerts.find_active(tenant_id, alert_key)
                if state is None:
                    raise RuntimeError("invoice gate alert state was not persisted")

            if is_new:
                if state.alert_id != candidate_alert_id:
                    unchanged += 1
                    retried += 1
                else:
                    created += 1
                    events.append(self._alert_event(state))
            else:
                unchanged += 1
                retried += 1
            await self._enqueue_alert_event(state)

        for alert_key, state in active.items():
            if alert_key in current:
                continue
            event_id = str(uuid5(NAMESPACE_URL, f"{state.alert_id}:resolved"))
            resolved_at = now.isoformat()
            payload = {
                "alert_id": state.alert_id,
                "alert_key": state.alert_key,
                "type": state.type,
                "severity": state.severity,
                "message": state.message,
                "value": state.value,
                "claim_id": state.claim_id,
                "actor_id": state.actor_id,
                "occurrence": state.occurrence,
                "resolution": "condition_cleared",
                "resolved_at": resolved_at,
            }
            await self._outbox.enqueue(
                EventEnvelope(
                    event_id=event_id,
                    event_type="expense.invoice.gate_alert_resolved.v1",
                    tenant_id=tenant_id,
                    task_id=state.claim_id or tenant_id,
                    trace_id=event_id,
                    producer="expense-invoice-service",
                    payload=payload,
                )
            )
            state.resolve(now)
            await self._alerts.save(state)
            resolved += 1
            events.append({"event_id": event_id, "event_type": "resolved", **payload})

        return {
            "tenant_id": tenant_id,
            "current": len(current),
            "created": created,
            "resolved": resolved,
            "unchanged": unchanged,
            "retried": retried,
            "emitted": created + resolved,
            "events": events,
        }

    async def scan_all_gate_alerts(self) -> dict[str, Any]:
        """扫描全部发票门禁告警。

        Returns:
            结构化结果字典。
        """
        tenants = await self._claims.list_tenants()
        results = [await self.emit_gate_alerts(tenant_id) for tenant_id in tenants]
        return {
            "tenants": len(results),
            "created": sum(int(result["created"]) for result in results),
            "resolved": sum(int(result["resolved"]) for result in results),
            "emitted": sum(int(result["emitted"]) for result in results),
            "results": results,
        }

    @staticmethod
    def _gate_alert_key(tenant_id: str, alert: InvoiceGateAlert) -> str:
        """执行门禁告警键。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            alert: 告警。

        Returns:
            字符串结果。
        """
        anchor = alert.anchor or str(int(alert.value))
        return (
            f"agentforge:{tenant_id}:invoice-gate-alert:{alert.type}:"
            f"{alert.claim_id or alert.actor_id}:{anchor}"
        )

    async def _enqueue_alert_event(self, state: InvoiceGateAlertState) -> None:
        """写入队列告警事件。

        Args:
            state: 当前状态。
        """
        await self._outbox.enqueue(
            EventEnvelope(
                event_id=state.alert_id,
                event_type="expense.invoice.gate_alert.v1",
                tenant_id=state.tenant_id,
                task_id=state.claim_id or state.tenant_id,
                trace_id=state.alert_id,
                producer="expense-invoice-service",
                payload=self._alert_payload(state),
            )
        )

    @staticmethod
    def _alert_payload(state: InvoiceGateAlertState) -> dict[str, Any]:
        """执行告警载荷。

        Args:
            state: 当前状态。

        Returns:
            结构化结果字典。
        """
        return {
            "alert_id": state.alert_id,
            "alert_key": state.alert_key,
            "type": state.type,
            "severity": state.severity,
            "message": state.message,
            "value": state.value,
            "claim_id": state.claim_id,
            "actor_id": state.actor_id,
            "occurrence": state.occurrence,
        }

    def _alert_event(self, state: InvoiceGateAlertState) -> dict[str, Any]:
        """执行告警事件。

        Args:
            state: 当前状态。

        Returns:
            结构化结果字典。
        """
        return {
            "event_id": state.alert_id,
            "event_type": "occurred",
            **self._alert_payload(state),
        }

    async def render_gate_metrics(self, tenant_id: str) -> str:
        """渲染门禁指标。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            字符串结果。
        """
        return _render_gate_metrics(
            [await self.gate_summary(tenant_id)],
            await self._alerts.list_all(tenant_id),
        )

    async def render_all_gate_metrics(self) -> str:
        """获取全部门禁指标。

        Returns:
            字符串结果。
        """
        tenants = sorted(
            set(await self._claims.list_tenants()) | set(await self._alerts.list_tenants())
        )
        summaries = [await self.gate_summary(tenant_id) for tenant_id in tenants]
        alert_history = [
            alert for tenant_id in tenants for alert in await self._alerts.list_all(tenant_id)
        ]
        return _render_gate_metrics(summaries, alert_history)

    async def _authorize(
        self,
        tenant_id: str,
        actor_id: str,
        action: str,
        resource_id: str,
    ) -> None:
        """授权报销发票。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            actor_id: 执行操作的参与者 ID。
            action: 待执行动作名称。
            resource_id: 资源 ID。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
            PermissionError: 调用方缺少所需权限时抛出。
        """
        if not actor_id.strip():
            raise ValueError("actor_id is required")
        decision = await self._authorization.authorize(
            tenant_id=tenant_id,
            principal=actor_id,
            action=action,
            resource_type="expense_invoice",
            resource_id=resource_id,
        )
        if decision.outcome != AuthorizationOutcome.ALLOWED:
            raise PermissionError("; ".join(decision.reasons))

    async def _record_event(self, invoice: ExpenseInvoice, event_type: str, actor_id: str) -> None:
        """记录事件。

        Args:
            invoice: 发票对象。
            event_type: 事件类型。
            actor_id: 执行操作的参与者 ID。
        """
        await self._record_invoice_audit(
            invoice,
            action=event_type.removesuffix(".v1"),
            actor_id=actor_id,
            risk_level=RiskLevel.LOW,
            payload={"claim_id": invoice.claim_id},
        )
        await self._publish_event(
            invoice,
            event_type=event_type,
            payload={
                "claim_id": invoice.claim_id,
                "invoice_number": invoice.invoice_number,
                "amount_cents": invoice.amount_cents,
            },
        )

    async def _record_invoice_audit(
        self,
        invoice: ExpenseInvoice,
        *,
        action: str,
        actor_id: str,
        risk_level: RiskLevel,
        payload: dict[str, Any],
    ) -> None:
        """记录发票审计。

        Args:
            invoice: 发票对象。
            action: 待执行动作名称。
            actor_id: 执行操作的参与者 ID。
            risk_level: 风险级别。
            payload: 事件、工作流或请求载荷。
        """
        await self._audit.save(
            AuditEvent(
                event_id=str(uuid4()),
                tenant_id=invoice.tenant_id,
                action=action,
                resource_type="expense_invoice",
                resource_id=invoice.invoice_id,
                risk_level=risk_level,
                actor_type="user",
                actor_id=actor_id,
                trace_id=str(invoice.metadata.get("trace_id") or uuid4()),
                payload=payload,
            )
        )

    async def _publish_event(
        self,
        invoice: ExpenseInvoice,
        *,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """发布事件。

        Args:
            invoice: 发票对象。
            event_type: 事件类型。
            payload: 事件、工作流或请求载荷。
        """
        await self._outbox.enqueue(
            EventEnvelope(
                event_id=str(uuid4()),
                event_type=event_type,
                tenant_id=invoice.tenant_id,
                task_id=invoice.invoice_id,
                trace_id=str(invoice.metadata.get("trace_id") or uuid4()),
                producer="expense-invoice-service",
                payload={"invoice_id": invoice.invoice_id, **payload},
            )
        )


def _invoice_from_payload(
    tenant_id: str,
    claim_id: str,
    payload: dict[str, Any],
    fingerprint: str,
) -> ExpenseInvoice:
    """从请求载荷构造发票领域对象。

    Args:
        tenant_id: 租户 ID，用于数据隔离。
        claim_id: 报销单 ID。
        payload: 事件、工作流或请求载荷。
        fingerprint: 指纹。

    Returns:
        报销发票结果。
    """
    return ExpenseInvoice(
        invoice_id=str(uuid4()),
        tenant_id=tenant_id,
        claim_id=claim_id,
        duplicate_key=fingerprint,
        fingerprint=fingerprint,
        invoice_code=str(payload["invoice_code"]),
        invoice_number=str(payload["invoice_number"]),
        invoice_date=date.fromisoformat(str(payload["invoice_date"])),
        amount_cents=int(payload["amount_cents"]),
        currency=str(payload["currency"]),
        seller_tax_id=str(payload["seller_tax_id"]),
        buyer_tax_id=str(payload["buyer_tax_id"]),
        metadata=dict(payload["metadata"]),
    )


def _match(invoice: ExpenseInvoice) -> InvoiceDuplicateMatch:
    """匹配对应记录。

    Args:
        invoice: 发票对象。

    Returns:
        发票重复匹配结果。
    """
    return InvoiceDuplicateMatch(
        invoice_id=invoice.invoice_id,
        claim_id=invoice.claim_id,
        fingerprint=invoice.fingerprint,
        invoice_number=invoice.invoice_number,
        amount_cents=invoice.amount_cents,
    )


def _verification_mismatch(invoice: ExpenseInvoice, data: dict[str, Any]) -> bool:
    """判断核验不一致是否成立。

    Args:
        invoice: 发票对象。
        data: 待处理数据。

    Returns:
        操作是否成功。
    """
    invoice_number = data.get("invoice_number")
    if invoice_number is not None and str(invoice_number) != invoice.invoice_number:
        return True
    seller_tax_id = data.get("seller_tax_id")
    if seller_tax_id is not None and str(seller_tax_id) != invoice.seller_tax_id:
        return True
    amount_cents = data.get("amount_cents")
    if amount_cents is not None and int(amount_cents) != invoice.amount_cents:
        return True
    return False


def _verification_ref(data: dict[str, Any]) -> str:
    """处理核验引用。

    Args:
        data: 待处理数据。

    Returns:
        字符串结果。
    """
    for key in ("verification_id", "reference", "request_id", "id"):
        value = data.get(key)
        if value is not None and str(value):
            return str(value)
    return ""


def _render_gate_metrics(
    summaries: list[InvoiceGateSummary],
    alert_history: list[InvoiceGateAlertState] | None = None,
) -> str:
    """渲染门禁指标。

    Args:
        summaries: 输入参数。
        alert_history: 告警历史。

    Returns:
        字符串结果。
    """
    lines = [
        "# HELP agentforge_expense_invoice_gate_claims Current claims by invoice readiness state.",
        "# TYPE agentforge_expense_invoice_gate_claims gauge",
    ]
    for summary in summaries:
        tenant = _prometheus_label(summary.tenant_id)
        lines.extend(
            [
                f'agentforge_expense_invoice_gate_claims{{tenant_id="{tenant}",state="ready"}} '
                f"{summary.ready_claims}",
                f'agentforge_expense_invoice_gate_claims{{tenant_id="{tenant}",'
                f'state="not_ready"}} {summary.not_ready_claims}',
            ]
        )
    lines.extend(
        [
            "# HELP agentforge_expense_invoice_gate_blocked_attempts "
            "Total blocked approval attempts.",
            "# TYPE agentforge_expense_invoice_gate_blocked_attempts gauge",
        ]
    )
    for summary in summaries:
        tenant = _prometheus_label(summary.tenant_id)
        lines.append(
            f'agentforge_expense_invoice_gate_blocked_attempts{{tenant_id="{tenant}"}} '
            f"{summary.blocked_attempts}"
        )
    lines.extend(
        [
            "# HELP agentforge_expense_invoice_gate_overrides "
            "Claims approved through invoice override.",
            "# TYPE agentforge_expense_invoice_gate_overrides gauge",
        ]
    )
    for summary in summaries:
        tenant = _prometheus_label(summary.tenant_id)
        lines.append(
            f'agentforge_expense_invoice_gate_overrides{{tenant_id="{tenant}"}} '
            f"{summary.override_claims}"
        )
    lines.extend(
        [
            "# HELP agentforge_expense_invoice_gate_oldest_block_age_seconds "
            "Age of oldest blocked claim.",
            "# TYPE agentforge_expense_invoice_gate_oldest_block_age_seconds gauge",
        ]
    )
    for summary in summaries:
        tenant = _prometheus_label(summary.tenant_id)
        lines.append(
            f'agentforge_expense_invoice_gate_oldest_block_age_seconds{{tenant_id="{tenant}"}} '
            f"{summary.oldest_blocked_age_seconds:.3f}"
        )
    lines.extend(
        [
            "# HELP agentforge_expense_invoice_gate_reason_claims "
            "Claims currently blocked by reason.",
            "# TYPE agentforge_expense_invoice_gate_reason_claims gauge",
        ]
    )
    for summary in summaries:
        tenant = _prometheus_label(summary.tenant_id)
        for reason, count in sorted(summary.reason_counts.items()):
            lines.append(
                f'agentforge_expense_invoice_gate_reason_claims{{tenant_id="{tenant}",'
                f'reason="{_prometheus_label(reason)}"}} {count}'
            )
    lines.extend(
        [
            "# HELP agentforge_expense_invoice_gate_alert "
            "Active invoice gate operational alerts.",
            "# TYPE agentforge_expense_invoice_gate_alert gauge",
        ]
    )
    for summary in summaries:
        tenant = _prometheus_label(summary.tenant_id)
        for alert in summary.alerts:
            lines.append(
                f'agentforge_expense_invoice_gate_alert{{tenant_id="{tenant}",'
                f'type="{_prometheus_label(alert.type)}",'
                f'severity="{_prometheus_label(alert.severity)}"}} 1'
            )
    occurrence_counts: dict[tuple[str, str], int] = {}
    state_counts: dict[tuple[str, str, str], int] = {}
    for state in alert_history or []:
        occurrence_key = (state.tenant_id, state.type)
        occurrence_counts[occurrence_key] = occurrence_counts.get(occurrence_key, 0) + 1
        state_key = (state.tenant_id, state.type, state.status.value)
        state_counts[state_key] = state_counts.get(state_key, 0) + 1
    lines.extend(
        [
            "# HELP agentforge_expense_invoice_gate_alert_occurrences "
            "Persisted invoice gate alert occurrences.",
            "# TYPE agentforge_expense_invoice_gate_alert_occurrences gauge",
        ]
    )
    for (tenant_id, alert_type), count in sorted(occurrence_counts.items()):
        lines.append(
            "agentforge_expense_invoice_gate_alert_occurrences"
            f'{{tenant_id="{_prometheus_label(tenant_id)}",'
            f'type="{_prometheus_label(alert_type)}"}} {count}'
        )
    lines.extend(
        [
            "# HELP agentforge_expense_invoice_gate_alert_state "
            "Persisted invoice gate alert states.",
            "# TYPE agentforge_expense_invoice_gate_alert_state gauge",
        ]
    )
    for (tenant_id, alert_type, state_name), count in sorted(state_counts.items()):
        lines.append(
            "agentforge_expense_invoice_gate_alert_state"
            f'{{tenant_id="{_prometheus_label(tenant_id)}",'
            f'type="{_prometheus_label(alert_type)}",'
            f'state="{_prometheus_label(state_name)}"}} {count}'
        )
    return "\n".join(lines) + "\n"


def _prometheus_label(value: str) -> str:
    """将标签值转换为 Prometheus 安全格式。

    Args:
        value: 待处理值。

    Returns:
        字符串结果。
    """
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
