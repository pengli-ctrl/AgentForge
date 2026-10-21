"""测试报销发票测试模块。"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.application.connector_registry import Connector
from agentforge.platform.domain.connector import (
    ConnectorContext,
    ConnectorHealth,
    ConnectorInvocationResult,
    ConnectorKind,
    ConnectorSpec,
)
from agentforge.platform.domain.rbac import Role, RoleAssignment
from agentforge.platform.infrastructure.db.base import Base
from agentforge.platform.infrastructure.outbox_dispatcher import OutboxDispatcher
from agentforge.platform.modules.expense.domain.invoice import (
    ExpenseInvoice,
    ExpenseInvoiceStatus,
    InvoiceGateAlertState,
)
from agentforge.platform.modules.expense.infrastructure.sqlalchemy_invoice_gate_alert_repository import (  # noqa: E501
    SQLAlchemyExpenseInvoiceGateAlertRepository,
)
from agentforge.platform.modules.expense.infrastructure.sqlalchemy_invoice_repository import (
    SQLAlchemyExpenseInvoiceRepository,
)
from agentforge.platform.modules.expense.runtime import get_expense_runtime
from agentforge.platform.modules.support.domain.ticket import TicketStatus
from agentforge.platform.modules.support.infrastructure.memory_repository import (
    MemoryTicketRepository,
)
from agentforge.platform.runtime import build_memory_container
from agentforge.platform.settings import get_settings


class FakeInvoiceConnector(Connector):
    """模拟发票连接器实现。"""

    name = "invoice-connector"
    version = "1.0"
    risk_level = "medium"

    def __init__(self) -> None:
        """初始化模拟发票。"""
        self.calls: list[dict] = []
        self.valid = True
        self.amount_override: int | None = None
        self.fail = False

    async def health(self) -> ConnectorHealth:
        """检查模拟发票健康状态。

        Returns:
            连接器健康结果。
        """
        return ConnectorHealth(connector_id="invoice-connector", healthy=True)

    async def invoke(
        self,
        action: str,
        payload: dict,
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        """调用模拟发票。

        Args:
            action: 待执行动作名称。
            payload: 事件、工作流或请求载荷。
            context: 执行上下文。

        Returns:
            连接器结果结果。
        """
        self.calls.append({"action": action, "payload": payload, "context": context})
        if self.fail:
            return ConnectorInvocationResult(
                connector_id="invoice-connector",
                action=action,
                ok=False,
                error="invoice service unavailable",
            )
        return ConnectorInvocationResult(
            connector_id="invoice-connector",
            action=action,
            ok=True,
            data={
                "valid": self.valid,
                "invoice_number": payload["invoice_number"],
                "seller_tax_id": payload["seller_tax_id"],
                "amount_cents": (
                    self.amount_override
                    if self.amount_override is not None
                    else payload["amount_cents"]
                ),
                "provider": "fake-tax-platform",
                "verification_id": "VERIFY-1",
                "message": "checked",
            },
        )

    async def compensate(
        self,
        action: str,
        payload: dict,
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        """补偿模拟发票。

        Args:
            action: 待执行动作名称。
            payload: 事件、工作流或请求载荷。
            context: 执行上下文。

        Returns:
            连接器结果结果。
        """
        return ConnectorInvocationResult(
            connector_id="invoice-connector",
            action=action,
            ok=True,
        )


class RecordingPublisher:
    """记录发布器相关组件。"""

    def __init__(self) -> None:
        """初始化记录发布器。"""
        self.events: list[object] = []

    async def publish(self, event: object) -> None:
        """发布记录发布器。

        Args:
            event: 待处理事件。
        """
        self.events.append(event)


def _invoice(number: str = "INV-001") -> dict:
    """处理发票。

    Args:
        number: 输入参数。

    Returns:
        结构化结果字典。
    """
    return {
        "invoice_code": "044001",
        "invoice_number": number,
        "invoice_date": "2026-10-18",
        "amount_cents": 12800,
        "currency": "CNY",
        "seller_tax_id": "91310000TEST",
        "buyer_tax_id": "91310000BUYER",
    }


def _client(
    *,
    verify_permission: bool = True,
    support_ticket_repository: MemoryTicketRepository | None = None,
) -> tuple[TestClient, FakeInvoiceConnector, object]:
    """处理客户端。

    Args:
        verify_permission: 校验权限。
        support_ticket_repository: 客服工单仓储。

    Returns:
        结果元组。
    """
    container = build_memory_container()
    connector = FakeInvoiceConnector()
    container.connector_registry.register(
        ConnectorSpec(
            connector_id="invoice-connector",
            tenant_id="tenant-invoice",
            name="invoice-connector",
            kind=ConnectorKind.OPENAPI,
            allowed_actions=["invoice.verify"],
        ),
        connector,
    )
    permissions = ["expense.invoice.write", "expense.invoice.release"]
    if verify_permission:
        permissions.append("expense.invoice.verify")
    asyncio.run(
        container.rbac_repository.save_role(
            Role(
                role_id="invoice-operator",
                tenant_id="tenant-invoice",
                name="invoice_operator",
                permissions=permissions,
            )
        )
    )
    asyncio.run(
        container.rbac_repository.save_assignment(
            RoleAssignment(
                assignment_id="invoice-operator-assignment",
                tenant_id="tenant-invoice",
                user_id="invoice-operator-user",
                role_id="invoice-operator",
            )
        )
    )
    return (
        TestClient(
            create_platform_app(
                container,
                support_ticket_repository=support_ticket_repository,
            )
        ),
        connector,
        container,
    )


def _claim(client: TestClient, key: str, *, tenant_id: str = "tenant-invoice") -> dict:
    """处理报销单。

    Args:
        client: 客户端实例。
        key: 缓存或配置键。
        tenant_id: 租户 ID，用于数据隔离。

    Returns:
        结构化结果字典。
    """
    response = client.post(
        "/v1/expense/claims",
        json={
            "tenant_id": tenant_id,
            "applicant_id": "employee-invoice",
            "amount_cents": 12800,
            "expense_date": "2026-10-18",
            "category": "travel",
            "description": "Invoice claim",
            "idempotency_key": key,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _register(client: TestClient, claim_id: str, invoice: dict) -> dict:
    """注册组件。

    Args:
        client: 客户端实例。
        claim_id: 报销单 ID。
        invoice: 发票对象。

    Returns:
        结构化结果字典。
    """
    response = client.post(
        f"/v1/expense/claims/{claim_id}/invoices",
        json={
            "tenant_id": "tenant-invoice",
            "actor_id": "invoice-operator-user",
            "invoices": [invoice],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["invoices"][0]


def _add_approver(container: object, *, with_override: bool = False) -> None:
    """添加审批人。

    Args:
        container: 服务容器。
        with_override: 使用覆盖。
    """
    permissions = ["expense.claim.approve"]
    if with_override:
        permissions.append("expense.invoice.override")
    asyncio.run(
        container.rbac_repository.save_role(
            Role(
                role_id="invoice-approver",
                tenant_id="tenant-invoice",
                name="invoice_approver",
                permissions=permissions,
            )
        )
    )
    asyncio.run(
        container.rbac_repository.save_assignment(
            RoleAssignment(
                assignment_id="invoice-approver-assignment",
                tenant_id="tenant-invoice",
                user_id="invoice-approver-user",
                role_id="invoice-approver",
            )
        )
    )


def test_invoice_registration_and_duplicate_detection() -> None:
    """验证发票注册及重复对应的测试场景。"""
    client, _, _ = _client()
    first_claim = _claim(client, "invoice-claim-1")
    second_claim = _claim(client, "invoice-claim-2")
    invoice = _register(client, first_claim["claim_id"], _invoice())

    variant = _invoice()
    variant["seller_tax_id"] = "91310000test"
    duplicate_check = client.post(
        "/v1/expense/invoices/check-duplicate",
        json={"tenant_id": "tenant-invoice", "invoices": [variant]},
    )
    assert duplicate_check.status_code == 200
    assert duplicate_check.json()["duplicates_found"] == 1
    assert duplicate_check.json()["items"][0]["match"]["invoice_id"] == invoice["invoice_id"]

    duplicate_register = client.post(
        f"/v1/expense/claims/{second_claim['claim_id']}/invoices",
        json={
            "tenant_id": "tenant-invoice",
            "actor_id": "invoice-operator-user",
            "invoices": [_invoice()],
        },
    )
    assert duplicate_register.status_code == 409
    assert "duplicate invoice" in duplicate_register.json()["detail"]
    stored_claim = client.get(
        f"/v1/expense/claims/{first_claim['claim_id']}",
        params={"tenant_id": "tenant-invoice"},
    ).json()
    assert stored_claim["invoice_count"] == 1


def test_released_invoice_can_be_reused_by_another_claim() -> None:
    """验证已释放发票可以为由另一个报销单对应的测试场景。"""
    client, _, _ = _client()
    first_claim = _claim(client, "invoice-release-1")
    second_claim = _claim(client, "invoice-release-2")
    invoice = _register(client, first_claim["claim_id"], _invoice("INV-RELEASE"))

    released = client.post(
        f"/v1/expense/invoices/{invoice['invoice_id']}/release",
        json={
            "tenant_id": "tenant-invoice",
            "actor_id": "invoice-operator-user",
            "reason": "wrong claim selected",
        },
    )
    assert released.status_code == 200
    assert released.json()["status"] == ExpenseInvoiceStatus.RELEASED.value
    assert released.json()["duplicate_key"] is None

    reused = _register(client, second_claim["claim_id"], _invoice("INV-RELEASE"))
    assert reused["invoice_id"] != invoice["invoice_id"]
    assert reused["claim_id"] == second_claim["claim_id"]


def test_invoice_verification_requires_permission() -> None:
    """验证发票核验要求权限对应的测试场景。"""
    client, connector, _ = _client(verify_permission=False)
    claim = _claim(client, "invoice-verify-denied")
    invoice = _register(client, claim["claim_id"], _invoice("INV-DENIED"))

    denied = client.post(
        f"/v1/expense/invoices/{invoice['invoice_id']}/verify",
        json={
            "tenant_id": "tenant-invoice",
            "connector_id": "invoice-connector",
            "actor_id": "invoice-operator-user",
        },
    )

    assert denied.status_code == 403
    assert connector.calls == []


def test_claim_rejection_releases_linked_invoices() -> None:
    """验证报销单发票对应的测试场景。"""
    client, _, container = _client()
    claim = _claim(client, "invoice-reject-release")
    invoice = _register(client, claim["claim_id"], _invoice("INV-REJECT"))
    asyncio.run(
        container.rbac_repository.save_role(
            Role(
                role_id="invoice-approver",
                tenant_id="tenant-invoice",
                name="invoice_approver",
                permissions=["expense.claim.approve"],
            )
        )
    )
    asyncio.run(
        container.rbac_repository.save_assignment(
            RoleAssignment(
                assignment_id="invoice-approver-assignment",
                tenant_id="tenant-invoice",
                user_id="invoice-approver-user",
                role_id="invoice-approver",
            )
        )
    )
    submitted = client.post(
        f"/v1/expense/claims/{claim['claim_id']}/submit",
        json={"tenant_id": "tenant-invoice"},
    )
    assert submitted.status_code == 200

    rejected = client.post(
        f"/v1/expense/claims/{claim['claim_id']}/decision",
        json={
            "tenant_id": "tenant-invoice",
            "decided_by": "invoice-approver-user",
            "decision": "reject",
            "reason": "duplicate reimbursement",
        },
    )
    assert rejected.status_code == 200, rejected.text
    claim_after = rejected.json()
    assert claim_after["status"] == "rejected"
    assert claim_after["invoice_count"] == 0
    assert claim_after["metadata"]["invoice_release"]["status"] == "released"
    invoices = client.get(
        f"/v1/expense/claims/{claim['claim_id']}/invoices",
        params={"tenant_id": "tenant-invoice"},
    ).json()["invoices"]
    assert invoices[0]["invoice_id"] == invoice["invoice_id"]
    assert invoices[0]["status"] == ExpenseInvoiceStatus.RELEASED.value


def test_verified_mode_blocks_approval_until_invoice_is_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证已验证模式阻止审批发票是否已验证对应的测试场景。

    Args:
        monkeypatch: pytest 提供的猴子补丁对象。
    """
    monkeypatch.setenv("AGENTFORGE_EXPENSE_INVOICE_ENFORCEMENT", "verified")
    monkeypatch.setenv("AGENTFORGE_EXPENSE_INVOICE_BLOCK_ALERT_HOURS", "0")
    get_settings.cache_clear()
    try:
        client, _, container = _client()
        _add_approver(container)
        claim = _claim(client, "invoice-gate-verified")
        invoice = _register(client, claim["claim_id"], _invoice("INV-GATE-1"))
        submit = client.post(
            f"/v1/expense/claims/{claim['claim_id']}/submit",
            json={"tenant_id": "tenant-invoice"},
        )
        assert submit.status_code == 200
        assert submit.json()["metadata"]["invoice_readiness"]["ready"] is False
        pending = asyncio.run(container.outbox_store.fetch_pending())
        assert any(event.event_type == "expense.invoice.readiness_changed.v1" for event in pending)
        readiness = client.get(
            f"/v1/expense/claims/{claim['claim_id']}/invoice-readiness",
            params={"tenant_id": "tenant-invoice"},
        ).json()
        assert readiness["ready"] is False
        assert any(reason.startswith("invoice_not_verified") for reason in readiness["reasons"])

        blocked = client.post(
            f"/v1/expense/claims/{claim['claim_id']}/decision",
            json={
                "tenant_id": "tenant-invoice",
                "decided_by": "invoice-approver-user",
                "decision": "approve",
                "reason": "checked",
            },
        )
        assert blocked.status_code == 403
        gate_summary = client.get(
            "/v1/expense/invoices/gate-summary",
            params={"tenant_id": "tenant-invoice"},
        ).json()
        assert gate_summary["blocked_attempts"] == 1
        assert gate_summary["reason_counts"]["invoice_not_verified"] == 1
        assert any(alert["type"] == "stale_invoice_gate_block" for alert in gate_summary["alerts"])
        metrics = client.get(
            "/v1/expense/invoices/gate-metrics",
            params={"tenant_id": "tenant-invoice"},
        )
        assert metrics.status_code == 200
        assert metrics.headers["content-type"].startswith("text/plain")
        assert "agentforge_expense_invoice_gate_blocked_attempts" in metrics.text
        platform_metrics = client.get("/metrics")
        assert platform_metrics.status_code == 200
        assert "agentforge_expense_invoice_gate_blocked_attempts" in platform_metrics.text
        audit = client.get(
            "/v1/audit",
            params={"tenant_id": "tenant-invoice", "resource_id": claim["claim_id"]},
        ).json()["events"]
        assert any(event["action"] == "expense.invoice.approval_blocked" for event in audit)
        verified = client.post(
            f"/v1/expense/invoices/{invoice['invoice_id']}/verify",
            json={
                "tenant_id": "tenant-invoice",
                "connector_id": "invoice-connector",
                "actor_id": "invoice-operator-user",
            },
        )
        assert verified.status_code == 200
        approved = client.post(
            f"/v1/expense/claims/{claim['claim_id']}/decision",
            json={
                "tenant_id": "tenant-invoice",
                "decided_by": "invoice-approver-user",
                "decision": "approve",
                "reason": "checked",
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["metadata"]["invoice_readiness"]["ready"] is True
    finally:
        get_settings.cache_clear()


def test_invoice_override_permission_allows_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证发票覆盖权限允许审批对应的测试场景。

    Args:
        monkeypatch: pytest 提供的猴子补丁对象。
    """
    monkeypatch.setenv("AGENTFORGE_EXPENSE_INVOICE_ENFORCEMENT", "verified")
    monkeypatch.setenv("AGENTFORGE_EXPENSE_INVOICE_OVERRIDE_ALERT_COUNT", "1")
    get_settings.cache_clear()
    try:
        client, _, container = _client()
        _add_approver(container, with_override=True)
        claim = _claim(client, "invoice-gate-override")
        _register(client, claim["claim_id"], _invoice("INV-GATE-OVERRIDE"))
        submitted = client.post(
            f"/v1/expense/claims/{claim['claim_id']}/submit",
            json={"tenant_id": "tenant-invoice"},
        )
        assert submitted.status_code == 200

        approved = client.post(
            f"/v1/expense/claims/{claim['claim_id']}/decision",
            json={
                "tenant_id": "tenant-invoice",
                "decided_by": "invoice-approver-user",
                "decision": "approve",
                "reason": "manager exception",
                "override_reason": "approved by CFO after manual tax-site check",
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        assert approved.json()["metadata"]["invoice_readiness"]["ready"] is False
        assert approved.json()["metadata"]["invoice_override"]["reason"] == (
            "approved by CFO after manual tax-site check"
        )
        summary = client.get(
            "/v1/expense/invoices/gate-summary",
            params={"tenant_id": "tenant-invoice"},
        ).json()
        assert summary["override_claims"] == 1
        assert any(alert["type"] == "frequent_invoice_override" for alert in summary["alerts"])
        metrics = client.get(
            "/v1/expense/invoices/gate-metrics",
            params={"tenant_id": "tenant-invoice"},
        )
        assert "agentforge_expense_invoice_gate_alert" in metrics.text
        pending = asyncio.run(container.outbox_store.fetch_pending())
        assert any(event.event_type == "expense.invoice.override_used.v1" for event in pending)
    finally:
        get_settings.cache_clear()


def test_strict_mode_blocks_invoice_amount_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证模式阻止发票金额不一致对应的测试场景。

    Args:
        monkeypatch: pytest 提供的猴子补丁对象。
    """
    monkeypatch.setenv("AGENTFORGE_EXPENSE_INVOICE_ENFORCEMENT", "strict")
    get_settings.cache_clear()
    try:
        client, _, container = _client()
        _add_approver(container)
        claim = _claim(client, "invoice-gate-strict")
        invoice_payload = _invoice("INV-GATE-STRICT")
        invoice_payload["amount_cents"] = 12000
        invoice = _register(client, claim["claim_id"], invoice_payload)
        client.post(
            f"/v1/expense/invoices/{invoice['invoice_id']}/verify",
            json={
                "tenant_id": "tenant-invoice",
                "connector_id": "invoice-connector",
                "actor_id": "invoice-operator-user",
            },
        )
        client.post(
            f"/v1/expense/claims/{claim['claim_id']}/submit",
            json={"tenant_id": "tenant-invoice"},
        )
        readiness = client.get(
            f"/v1/expense/claims/{claim['claim_id']}/invoice-readiness",
            params={"tenant_id": "tenant-invoice"},
        ).json()
        assert "invoice_amount_mismatch" in readiness["reasons"]
        blocked = client.post(
            f"/v1/expense/claims/{claim['claim_id']}/decision",
            json={
                "tenant_id": "tenant-invoice",
                "decided_by": "invoice-approver-user",
                "decision": "approve",
                "reason": "checked",
            },
        )
        assert blocked.status_code == 403
    finally:
        get_settings.cache_clear()


def test_invoice_override_requires_structured_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证发票覆盖要求结构化原因对应的测试场景。

    Args:
        monkeypatch: pytest 提供的猴子补丁对象。
    """
    monkeypatch.setenv("AGENTFORGE_EXPENSE_INVOICE_ENFORCEMENT", "verified")
    get_settings.cache_clear()
    try:
        client, _, container = _client()
        _add_approver(container, with_override=True)
        claim = _claim(client, "invoice-gate-override-reason")
        _register(client, claim["claim_id"], _invoice("INV-GATE-REASON"))
        client.post(
            f"/v1/expense/claims/{claim['claim_id']}/submit",
            json={"tenant_id": "tenant-invoice"},
        )

        response = client.post(
            f"/v1/expense/claims/{claim['claim_id']}/decision",
            json={
                "tenant_id": "tenant-invoice",
                "decided_by": "invoice-approver-user",
                "decision": "approve",
                "reason": "manager exception",
            },
        )

        assert response.status_code == 409
        assert "override_reason" in response.json()["detail"]
        summary = client.get(
            "/v1/expense/invoices/gate-summary",
            params={"tenant_id": "tenant-invoice"},
        ).json()
        assert summary["blocked_attempts"] == 1
    finally:
        get_settings.cache_clear()


def test_stale_invoice_gate_alert_dispatches_to_support_ticket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证发票门禁告警分发到客服工单对应的测试场景。

    Args:
        monkeypatch: pytest 提供的猴子补丁对象。
    """
    monkeypatch.setenv("AGENTFORGE_EXPENSE_INVOICE_ENFORCEMENT", "verified")
    monkeypatch.setenv("AGENTFORGE_EXPENSE_INVOICE_BLOCK_ALERT_HOURS", "0")
    get_settings.cache_clear()
    try:
        ticket_repository = MemoryTicketRepository()
        client, _, container = _client(support_ticket_repository=ticket_repository)
        _add_approver(container)
        claim = _claim(client, "invoice-gate-ticket")
        _register(client, claim["claim_id"], _invoice("INV-GATE-TICKET"))
        client.post(
            f"/v1/expense/claims/{claim['claim_id']}/submit",
            json={"tenant_id": "tenant-invoice"},
        )
        client.post(
            f"/v1/expense/claims/{claim['claim_id']}/decision",
            json={
                "tenant_id": "tenant-invoice",
                "decided_by": "invoice-approver-user",
                "decision": "approve",
                "reason": "checked",
            },
        )
        scan = client.post(
            "/v1/expense/invoices/gate-alerts/scan",
            json={"tenant_id": "tenant-invoice"},
        )
        assert scan.status_code == 200
        assert scan.json()["emitted"] == 1

        publisher = RecordingPublisher()
        dispatcher = OutboxDispatcher(
            container.outbox_store,
            publisher,
            client.app.state.module_registry.event_handlers(),
        )
        dispatched = asyncio.run(dispatcher.dispatch_once(limit=100))
        assert dispatched >= 1
        tickets, _ = asyncio.run(ticket_repository.list("tenant-invoice"))
        assert len(tickets) == 1
        assert tickets[0].source == "expense-invoice-gate"
        assert tickets[0].metadata["alert_type"] == "stale_invoice_gate_block"
        assert tickets[0].metadata["claim_id"] == claim["claim_id"]
    finally:
        get_settings.cache_clear()


def test_invoice_gate_alert_lifecycle_resolves_and_reopens_ticket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证发票门禁告警生命周期及工单对应的测试场景。

    Args:
        monkeypatch: pytest 提供的猴子补丁对象。
    """
    monkeypatch.setenv("AGENTFORGE_EXPENSE_INVOICE_ENFORCEMENT", "verified")
    monkeypatch.setenv("AGENTFORGE_EXPENSE_INVOICE_BLOCK_ALERT_HOURS", "0")
    monkeypatch.setenv("AGENTFORGE_SUPPORT_INVOICE_GATE_TEAM", "finance-control")
    monkeypatch.setenv("AGENTFORGE_SUPPORT_INVOICE_GATE_SLA_MINUTES", "45")
    monkeypatch.setenv("AGENTFORGE_SUPPORT_INVOICE_GATE_ASSIGNEE", "finance-bot")
    get_settings.cache_clear()
    try:
        ticket_repository = MemoryTicketRepository()
        client, _, container = _client(support_ticket_repository=ticket_repository)
        _add_approver(container)
        claim = _claim(client, "invoice-gate-lifecycle")
        _register(client, claim["claim_id"], _invoice("INV-GATE-LIFECYCLE"))
        client.post(
            f"/v1/expense/claims/{claim['claim_id']}/submit",
            json={"tenant_id": "tenant-invoice"},
        )
        blocked = client.post(
            f"/v1/expense/claims/{claim['claim_id']}/decision",
            json={
                "tenant_id": "tenant-invoice",
                "decided_by": "invoice-approver-user",
                "decision": "approve",
                "reason": "checked",
            },
        )
        assert blocked.status_code == 403

        first = client.post(
            "/v1/expense/invoices/gate-alerts/scan",
            json={"tenant_id": "tenant-invoice"},
        ).json()
        second = client.post(
            "/v1/expense/invoices/gate-alerts/scan",
            json={"tenant_id": "tenant-invoice"},
        ).json()
        assert first["created"] == 1
        assert first["emitted"] == 1
        assert second["created"] == 0
        assert second["unchanged"] == 1
        first_alert_id = first["events"][0]["alert_id"]

        dispatcher = OutboxDispatcher(
            container.outbox_store,
            RecordingPublisher(),
            client.app.state.module_registry.event_handlers(),
        )
        assert asyncio.run(dispatcher.dispatch_once(limit=100)) >= 1
        tickets, _ = asyncio.run(ticket_repository.list("tenant-invoice"))
        assert len(tickets) == 1
        assert tickets[0].status == TicketStatus.WAITING_REVIEW
        assert tickets[0].assigned_team == "finance-control"
        assert tickets[0].assignee_id == "finance-bot"
        assert tickets[0].intent == "invoice_gate_exception"
        assert tickets[0].priority.value == "p2"
        assert tickets[0].metadata["queue"] == "finance-control"
        assert tickets[0].metadata["sla"]["minutes"] == 45
        assert tickets[0].metadata["occurrence"] == 1

        runtime = get_expense_runtime()
        stored_claim = asyncio.run(runtime.repository.get("tenant-invoice", claim["claim_id"]))
        assert stored_claim is not None
        stats = dict(stored_claim.metadata["invoice_gate_stats"])
        stored_claim.metadata = {
            key: value
            for key, value in stored_claim.metadata.items()
            if key != "invoice_gate_stats"
        }
        asyncio.run(runtime.repository.save(stored_claim))

        resolved = client.post(
            "/v1/expense/invoices/gate-alerts/scan",
            json={"tenant_id": "tenant-invoice"},
        ).json()
        assert resolved["created"] == 0
        assert resolved["resolved"] == 1
        assert resolved["emitted"] == 1
        pending = asyncio.run(container.outbox_store.fetch_pending())
        assert any(
            event.event_type == "expense.invoice.gate_alert_resolved.v1" for event in pending
        )
        assert asyncio.run(dispatcher.dispatch_once(limit=100)) >= 1
        cancelled = asyncio.run(ticket_repository.get("tenant-invoice", tickets[0].ticket_id))
        assert cancelled is not None
        assert cancelled.status == TicketStatus.CANCELLED
        assert cancelled.metadata["resolution"]["alert_type"] == "stale_invoice_gate_block"

        stored_claim = asyncio.run(runtime.repository.get("tenant-invoice", claim["claim_id"]))
        assert stored_claim is not None
        stored_claim.metadata["invoice_gate_stats"] = stats
        asyncio.run(runtime.repository.save(stored_claim))
        reopened = client.post(
            "/v1/expense/invoices/gate-alerts/scan",
            json={"tenant_id": "tenant-invoice"},
        ).json()
        assert reopened["created"] == 1
        assert reopened["events"][0]["alert_id"] != first_alert_id
        assert reopened["events"][0]["occurrence"] == 2
        assert asyncio.run(dispatcher.dispatch_once(limit=100)) >= 1
        tickets, _ = asyncio.run(ticket_repository.list("tenant-invoice"))
        open_tickets = [ticket for ticket in tickets if ticket.status != TicketStatus.CANCELLED]
        assert len(open_tickets) == 1
        assert open_tickets[0].metadata["occurrence"] == 2
        metrics = client.get("/metrics").text
        assert "agentforge_expense_invoice_gate_alert_occurrences" in metrics
        assert "agentforge_support_ticket_sla_open" in metrics
        assert 'team="finance-control"' in metrics
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_sqlalchemy_invoice_gate_alert_repository_round_trip() -> None:
    """验证SQLAlchemy发票门禁告警仓储轮次往返对应的测试场景。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repository = SQLAlchemyExpenseInvoiceGateAlertRepository(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    alert = InvoiceGateAlertState(
        alert_id="alert-sql",
        tenant_id="tenant-invoice",
        alert_key="key-sql",
        type="stale_invoice_gate_block",
        severity="warning",
        message="blocked too long",
        value=1.0,
        claim_id="claim-1",
    )

    await repository.save(alert)
    active = await repository.find_active("tenant-invoice", "key-sql")
    alert.resolve()
    await repository.save(alert)

    assert active is not None
    assert active.alert_id == "alert-sql"
    assert await repository.count_occurrences("tenant-invoice", "key-sql") == 1
    assert len(await repository.list_all("tenant-invoice")) == 1
    assert await repository.list_tenants() == ["tenant-invoice"]
    assert await repository.list_active("tenant-invoice") == []
    stored = await repository.get("tenant-invoice", "alert-sql")
    assert stored is not None
    assert stored.resolved_at is not None
    await engine.dispose()


def test_invoice_verification_success_and_mismatch() -> None:
    """验证发票核验成功及不一致对应的测试场景。"""
    client, connector, container = _client()
    claim = _claim(client, "invoice-verify-1")
    invoice = _register(client, claim["claim_id"], _invoice("INV-VERIFY"))

    verified = client.post(
        f"/v1/expense/invoices/{invoice['invoice_id']}/verify",
        json={
            "tenant_id": "tenant-invoice",
            "connector_id": "invoice-connector",
            "actor_id": "invoice-operator-user",
        },
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "verified"
    assert verified.json()["provider"] == "fake-tax-platform"
    assert verified.json()["verification_ref"] == "VERIFY-1"
    assert connector.calls[0]["payload"]["invoice_number"] == "INV-VERIFY"
    pending = asyncio.run(container.outbox_store.fetch_pending())
    assert any(event.event_type == "expense.invoice.verification_verified.v1" for event in pending)
    audit = client.get(
        "/v1/audit",
        params={"tenant_id": "tenant-invoice", "resource_id": invoice["invoice_id"]},
    ).json()["events"]
    assert any(event["action"] == "expense.invoice.verification_verified" for event in audit)

    second = _register(client, claim["claim_id"], _invoice("INV-MISMATCH"))
    connector.amount_override = 12000
    mismatch = client.post(
        f"/v1/expense/invoices/{second['invoice_id']}/verify",
        json={
            "tenant_id": "tenant-invoice",
            "connector_id": "invoice-connector",
            "actor_id": "invoice-operator-user",
        },
    )
    assert mismatch.status_code == 200
    assert mismatch.json()["status"] == "mismatch"


@pytest.mark.asyncio
async def test_sqlalchemy_invoice_repository_round_trip() -> None:
    """验证SQLAlchemy发票仓储轮次往返对应的测试场景。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repository = SQLAlchemyExpenseInvoiceRepository(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    invoice = ExpenseInvoice(
        invoice_id="invoice-sql",
        tenant_id="tenant-invoice",
        claim_id="claim-1",
        duplicate_key="fingerprint-sql",
        fingerprint="fingerprint-sql",
        invoice_number="INV-SQL",
        invoice_date=date(2026, 10, 18),
        amount_cents=12800,
    )

    await repository.save(invoice)
    stored = await repository.get("tenant-invoice", invoice.invoice_id)
    duplicate = await repository.get_active_by_fingerprint(
        "tenant-invoice",
        invoice.fingerprint,
    )

    assert stored is not None
    assert stored.invoice_number == "INV-SQL"
    assert duplicate is not None
    assert duplicate.invoice_id == invoice.invoice_id
    await engine.dispose()
