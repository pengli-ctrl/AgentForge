"""测试报销台账写回测试模块。"""

from __future__ import annotations

import asyncio
import csv
import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.application.builtin_policies import seed_rbac
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
from agentforge.platform.infrastructure.memory_rbac_repository import MemoryRbacRepository
from agentforge.platform.modules.expense.domain.ledger import (
    ExpenseWritebackItem,
    ExpenseWritebackStatus,
)
from agentforge.platform.modules.expense.domain.writeback_job import ExpenseWritebackJob
from agentforge.platform.modules.expense.infrastructure.sqlalchemy_writeback_job_repository import (
    SQLAlchemyExpenseWritebackJobRepository,
)
from agentforge.platform.runtime import build_memory_container


class FakeLedgerConnector(Connector):
    """用于模拟 ERP 台账集成的连接器。"""

    name = "erp-ledger"
    version = "1.0"
    risk_level = "high"

    def __init__(self) -> None:
        """初始化模拟台账。"""
        self.calls: list[dict] = []
        self.compensation_calls: list[dict] = []
        self.fail = False
        self.fail_claim_ids: set[str] = set()
        self.lookup_found = True
        self.lookup_external_id_override: str | None = None
        self.lookup_amount_override: int | None = None
        self.fail_compensation = False

    async def health(self) -> ConnectorHealth:
        """检查模拟台账健康状态。

        Returns:
            连接器健康结果。
        """
        return ConnectorHealth(connector_id="erp-ledger", healthy=True)

    async def invoke(
        self,
        action: str,
        payload: dict,
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        """调用模拟台账。

        Args:
            action: 待执行动作名称。
            payload: 事件、工作流或请求载荷。
            context: 执行上下文。

        Returns:
            连接器结果结果。
        """
        self.calls.append(
            {
                "action": action,
                "payload": payload,
                "context": context,
            }
        )
        if self.fail or payload["claim_id"] in self.fail_claim_ids:
            return ConnectorInvocationResult(
                connector_id="erp-ledger",
                action=action,
                ok=False,
                error="ERP temporarily unavailable",
            )
        if action == "ledger.lookup":
            return ConnectorInvocationResult(
                connector_id="erp-ledger",
                action=action,
                ok=True,
                data={
                    "found": self.lookup_found,
                    "voucher_id": self.lookup_external_id_override
                    or payload["expected_external_id"],
                    "amount_cents": (
                        self.lookup_amount_override
                        if self.lookup_amount_override is not None
                        else payload["expected_amount_cents"]
                    ),
                    "status": "posted",
                },
            )
        return ConnectorInvocationResult(
            connector_id="erp-ledger",
            action=action,
            ok=True,
            data={"voucher_id": f"V-{payload['claim_id']}"},
        )

    async def compensate(
        self,
        action: str,
        payload: dict,
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        """补偿模拟台账。

        Args:
            action: 待执行动作名称。
            payload: 事件、工作流或请求载荷。
            context: 执行上下文。

        Returns:
            连接器结果结果。
        """
        self.compensation_calls.append({"action": action, "payload": payload, "context": context})
        if self.fail_compensation:
            return ConnectorInvocationResult(
                connector_id="erp-ledger",
                action=action,
                ok=False,
                error="ERP compensation failed",
            )
        return ConnectorInvocationResult(
            connector_id="erp-ledger",
            action=action,
            ok=True,
            data={"compensation_id": f"C-{payload['external_id']}"},
        )


class FakeWorkflowClient:
    """记录工作流调用的测试客户端。"""

    def __init__(self) -> None:
        """初始化模拟。"""
        self.calls: list[dict] = []

    async def start_workflow(self, workflow, arg, **kwargs):
        """启动工作流。

        Args:
            workflow: 工作流定义或实例。
            arg: 输入参数。
            kwargs: 关键字参数。

        Returns:
            处理结果。
        """
        self.calls.append({"workflow": workflow, "arg": arg, **kwargs})
        return kwargs.get("workflow_id") or "workflow-1"

    async def signal_workflow(self, workflow_id, signal, arg=None) -> None:
        """发送信号工作流。

        Args:
            workflow_id: 工作流 ID。
            signal: 信号。
            arg: 输入参数。
        """
        return None


def _client_and_connector(
    *,
    ledger_permission: bool = True,
    workflow_client=None,
) -> tuple[TestClient, FakeLedgerConnector, object]:
    """处理客户端及连接器。

    Args:
        ledger_permission: 台账权限。
        workflow_client: 工作流客户端。

    Returns:
        结果元组。
    """
    container = build_memory_container(workflow_client=workflow_client)
    connector = FakeLedgerConnector()
    container.connector_registry.register(
        ConnectorSpec(
            connector_id="erp-ledger",
            tenant_id="tenant-ledger",
            name="erp-ledger",
            kind=ConnectorKind.OPENAPI,
            allowed_actions=["ledger.post", "ledger.lookup", "ledger.compensate"],
        ),
        connector,
    )
    permissions = ["expense.claim.approve"]
    if ledger_permission:
        permissions.extend(
            [
                "expense.ledger.writeback",
                "expense.ledger.verify",
                "expense.ledger.compensate",
            ]
        )
    asyncio.run(
        container.rbac_repository.save_role(
            Role(
                role_id="ledger-writer",
                tenant_id="tenant-ledger",
                name="ledger_writer",
                permissions=permissions,
            )
        )
    )
    asyncio.run(
        container.rbac_repository.save_assignment(
            RoleAssignment(
                assignment_id="ledger-writer-assignment",
                tenant_id="tenant-ledger",
                user_id="ledger-writer-user",
                role_id="ledger-writer",
            )
        )
    )
    return TestClient(create_platform_app(container)), connector, container


def _approved_claim(
    client: TestClient,
    key: str,
    *,
    tenant_id: str = "tenant-ledger",
    amount_cents: int = 12800,
    description: str = "Client visit",
) -> dict:
    """处理已批准报销单。

    Args:
        client: 客户端实例。
        key: 缓存或配置键。
        tenant_id: 租户 ID，用于数据隔离。
        amount_cents: 金额分。
        description: 输入参数。

    Returns:
        结构化结果字典。
    """
    created = client.post(
        "/v1/expense/claims",
        json={
            "tenant_id": tenant_id,
            "applicant_id": "employee-ledger",
            "amount_cents": amount_cents,
            "currency": "CNY",
            "expense_date": "2026-10-18",
            "category": "travel",
            "description": description,
            "invoice_count": 1,
            "idempotency_key": key,
        },
    )
    assert created.status_code == 200, created.text
    claim = created.json()
    submitted = client.post(
        f"/v1/expense/claims/{claim['claim_id']}/submit",
        json={"tenant_id": tenant_id},
    )
    assert submitted.status_code == 200, submitted.text
    approved = client.post(
        f"/v1/expense/claims/{claim['claim_id']}/decision",
        json={
            "tenant_id": tenant_id,
            "decided_by": "ledger-writer-user",
            "decision": "approve",
            "reason": "receipt verified",
        },
    )
    assert approved.status_code == 200, approved.text
    return approved.json()


def _writeback_claim(client: TestClient, claim: dict) -> dict:
    """处理写回报销单。

    Args:
        client: 客户端实例。
        claim: 报销单对象。

    Returns:
        结构化结果字典。
    """
    response = client.post(
        "/v1/expense/ledger/writeback",
        json={
            "tenant_id": "tenant-ledger",
            "connector_id": "erp-ledger",
            "actor_id": "ledger-writer-user",
            "claim_ids": [claim["claim_id"]],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_expense_ledger_exports_tenant_scoped_csv_and_json() -> None:
    """验证报销台账导出租户按范围隔离CSV及JSON对应的测试场景。"""
    client, _, _ = _client_and_connector()
    first = _approved_claim(client, "ledger-export-1", amount_cents=1000)
    formula = _approved_claim(
        client,
        "ledger-export-formula",
        amount_cents=500,
        description='=HYPERLINK("https://example.test")',
    )
    second = _approved_claim(client, "ledger-export-2", amount_cents=2500)

    exported = client.get(
        "/v1/expense/ledger/export",
        params={"tenant_id": "tenant-ledger", "format": "csv"},
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "expense-ledger-tenant-ledger.csv" in exported.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))
    assert {row["claim_id"] for row in rows} == {
        first["claim_id"],
        formula["claim_id"],
        second["claim_id"],
    }
    assert {row["writeback_status"] for row in rows} == {"pending"}
    assert sum(int(row["amount_cents"]) for row in rows) == 4000
    formula_row = next(row for row in rows if row["claim_id"] == formula["claim_id"])
    assert formula_row["description"].startswith("'=HYPERLINK")

    json_export = client.get(
        "/v1/expense/ledger/export",
        params={"tenant_id": "tenant-ledger", "format": "json"},
    )
    assert json_export.status_code == 200
    assert len(json_export.json()["claims"]) == 3
    isolated = client.get(
        "/v1/expense/ledger/export",
        params={"tenant_id": "tenant-other", "format": "json"},
    )
    assert isolated.status_code == 200
    assert isolated.json()["claims"] == []


def test_ledger_writeback_is_idempotent_audited_and_reconciled() -> None:
    """验证台账写回是否幂等已审计及已核对对应的测试场景。"""
    client, connector, container = _client_and_connector()
    claim = _approved_claim(client, "ledger-writeback-1")
    payload = {
        "tenant_id": "tenant-ledger",
        "connector_id": "erp-ledger",
        "actor_id": "ledger-writer-user",
        "claim_ids": [claim["claim_id"]],
    }

    first = client.post("/v1/expense/ledger/writeback", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["succeeded"] == 1
    assert first.json()["items"][0]["external_id"] == f"V-{claim['claim_id']}"
    assert len(connector.calls) == 1
    assert connector.calls[0]["context"].idempotency_key == (
        f"expense-writeback:erp-ledger:ledger.post:{claim['claim_id']}"
    )

    replay = client.post("/v1/expense/ledger/writeback", json=payload)
    assert replay.status_code == 200
    assert replay.json()["skipped"] == 1
    assert replay.json()["items"][0]["idempotent_replay"] is True
    assert len(connector.calls) == 1

    stored = client.get(
        f"/v1/expense/claims/{claim['claim_id']}",
        params={"tenant_id": "tenant-ledger"},
    ).json()
    writeback = stored["metadata"]["writebacks"]["erp-ledger:ledger.post"]
    assert writeback["status"] == "succeeded"
    assert writeback["external_id"] == f"V-{claim['claim_id']}"

    audit = client.get(
        "/v1/audit",
        params={"tenant_id": "tenant-ledger", "resource_id": claim["claim_id"]},
    ).json()["events"]
    assert any(event["action"] == "expense.ledger.writeback_succeeded" for event in audit)
    pending = asyncio.run(container.outbox_store.fetch_pending())
    assert any(event.event_type == "expense.ledger.writeback_succeeded.v1" for event in pending)

    reconciliation = client.get(
        "/v1/expense/ledger/reconciliation",
        params={"tenant_id": "tenant-ledger", "connector_id": "erp-ledger"},
    ).json()
    assert reconciliation["written_claims"] == 1
    assert reconciliation["written_amount_cents"] == 12800
    assert reconciliation["pending_claims"] == 0
    assert reconciliation["failed_claims"] == 0


def test_ledger_writeback_failure_can_be_retried() -> None:
    """验证台账写回失败可以为已重试对应的测试场景。"""
    client, connector, _ = _client_and_connector()
    claim = _approved_claim(client, "ledger-writeback-retry")
    connector.fail = True
    payload = {
        "tenant_id": "tenant-ledger",
        "connector_id": "erp-ledger",
        "actor_id": "ledger-writer-user",
        "claim_ids": [claim["claim_id"]],
    }

    failed = client.post("/v1/expense/ledger/writeback", json=payload)
    assert failed.status_code == 200
    assert failed.json()["failed"] == 1
    assert failed.json()["items"][0]["error"] == "ERP temporarily unavailable"
    reconciliation = client.get(
        "/v1/expense/ledger/reconciliation",
        params={"tenant_id": "tenant-ledger"},
    ).json()
    assert reconciliation["failed_claims"] == 1
    assert reconciliation["issues"][0]["claim_id"] == claim["claim_id"]

    connector.fail = False
    retried = client.post("/v1/expense/ledger/writeback", json=payload)
    assert retried.status_code == 200
    assert retried.json()["succeeded"] == 1
    assert len(connector.calls) == 2
    after = client.get(
        "/v1/expense/ledger/reconciliation",
        params={"tenant_id": "tenant-ledger"},
    ).json()
    assert after["failed_claims"] == 0
    assert after["written_claims"] == 1


def test_ledger_writeback_requires_permission_and_reports_missing_claim() -> None:
    """验证台账写回要求权限及报告缺失报销单对应的测试场景。"""
    denied_client, denied_connector, _ = _client_and_connector(ledger_permission=False)
    claim = _approved_claim(denied_client, "ledger-writeback-denied")
    denied = denied_client.post(
        "/v1/expense/ledger/writeback",
        json={
            "tenant_id": "tenant-ledger",
            "connector_id": "erp-ledger",
            "actor_id": "ledger-writer-user",
            "claim_ids": [claim["claim_id"]],
        },
    )
    assert denied.status_code == 403
    assert denied_connector.calls == []

    allowed_client, _, _ = _client_and_connector()
    missing = allowed_client.post(
        "/v1/expense/ledger/writeback",
        json={
            "tenant_id": "tenant-ledger",
            "connector_id": "erp-ledger",
            "actor_id": "ledger-writer-user",
            "claim_ids": ["missing-claim"],
        },
    )
    assert missing.status_code == 200
    assert missing.json()["failed"] == 1
    assert missing.json()["items"][0]["error"] == "expense claim not found"


def test_seed_rbac_updates_existing_finance_role_with_writeback_permission() -> None:
    """验证初始化RBAC更新现有财务角色使用写回权限对应的测试场景。"""
    repository = MemoryRbacRepository()
    asyncio.run(
        repository.save_role(
            Role(
                role_id="role-finance-approver",
                tenant_id="*",
                name="finance_approver",
                permissions=["expense.claim.approve"],
                built_in=True,
            )
        )
    )

    asyncio.run(seed_rbac(repository))
    asyncio.run(seed_rbac(repository))

    role = asyncio.run(repository.get_role("*", "role-finance-approver"))
    assert role is not None
    assert role.permissions.count("expense.ledger.writeback") == 1
    assert role.permissions.count("expense.ledger.verify") == 1
    assert role.permissions.count("expense.ledger.compensate") == 1


def test_writeback_job_dispatches_to_expense_queue_and_is_queryable() -> None:
    """验证写回任务分发到报销队列及是否对应的测试场景。"""
    workflow_client = FakeWorkflowClient()
    client, connector, _ = _client_and_connector(workflow_client=workflow_client)
    claim = _approved_claim(client, "writeback-job-async")

    created = client.post(
        "/v1/expense/ledger/writeback-jobs",
        json={
            "tenant_id": "tenant-ledger",
            "connector_id": "erp-ledger",
            "actor_id": "ledger-writer-user",
        },
    )
    assert created.status_code == 200, created.text
    job = created.json()
    assert job["status"] == "queued"
    assert job["total_claims"] == 1
    assert job["claim_ids"] == [claim["claim_id"]]
    assert connector.calls == []
    assert workflow_client.calls[0]["task_queue"] == "expense-copilot"
    assert workflow_client.calls[0]["arg"] == {
        "tenant_id": "tenant-ledger",
        "job_id": job["job_id"],
    }

    listed = client.get(
        "/v1/expense/ledger/writeback-jobs",
        params={"tenant_id": "tenant-ledger"},
    ).json()
    assert [item["job_id"] for item in listed["jobs"]] == [job["job_id"]]
    summary = client.get(
        "/v1/expense/ledger/writeback-jobs/summary",
        params={"tenant_id": "tenant-ledger"},
    ).json()
    assert summary["total"] == 1
    assert summary["by_status"]["queued"] == 1
    detail = client.get(
        f"/v1/expense/ledger/writeback-jobs/{job['job_id']}",
        params={"tenant_id": "tenant-ledger"},
    )
    assert detail.status_code == 200
    isolated = client.get(
        f"/v1/expense/ledger/writeback-jobs/{job['job_id']}",
        params={"tenant_id": "tenant-other"},
    )
    assert isolated.status_code == 404


def test_partial_writeback_job_retries_failed_claims() -> None:
    """验证写回任务重试失败报销单对应的测试场景。"""
    client, connector, _ = _client_and_connector()
    first = _approved_claim(client, "writeback-job-first", amount_cents=1000)
    second = _approved_claim(client, "writeback-job-second", amount_cents=2000)
    connector.fail_claim_ids.add(second["claim_id"])

    created = client.post(
        "/v1/expense/ledger/writeback-jobs",
        json={
            "tenant_id": "tenant-ledger",
            "connector_id": "erp-ledger",
            "actor_id": "ledger-writer-user",
            "claim_ids": [first["claim_id"], second["claim_id"]],
        },
    )
    assert created.status_code == 200, created.text
    job = created.json()
    assert job["status"] == "partial_failed"
    assert job["succeeded_claims"] == 1
    assert job["failed_claims"] == 1
    assert job["attempts"] == 1

    connector.fail_claim_ids.clear()
    retried = client.post(
        f"/v1/expense/ledger/writeback-jobs/{job['job_id']}/retry-failed",
        json={"tenant_id": "tenant-ledger"},
    )
    assert retried.status_code == 200, retried.text
    retried_job = retried.json()
    assert retried_job["status"] == "succeeded"
    assert retried_job["succeeded_claims"] == 1
    assert retried_job["skipped_claims"] == 1
    assert retried_job["failed_claims"] == 0
    assert retried_job["attempts"] == 2


def test_writeback_job_requires_writeback_permission() -> None:
    """验证写回任务要求写回权限对应的测试场景。"""
    client, connector, _ = _client_and_connector(ledger_permission=False)
    _approved_claim(client, "writeback-job-denied")

    denied = client.post(
        "/v1/expense/ledger/writeback-jobs",
        json={
            "tenant_id": "tenant-ledger",
            "connector_id": "erp-ledger",
            "actor_id": "ledger-writer-user",
        },
    )

    assert denied.status_code == 403
    assert connector.calls == []


def test_external_voucher_verification_matches_writeback() -> None:
    """验证外部凭证核验匹配结果写回对应的测试场景。"""
    client, connector, container = _client_and_connector()
    claim = _approved_claim(client, "voucher-verification-match")
    _writeback_claim(client, claim)

    verified = client.post(
        "/v1/expense/ledger/writebacks/verify",
        json={
            "tenant_id": "tenant-ledger",
            "connector_id": "erp-ledger",
            "actor_id": "ledger-writer-user",
            "claim_ids": [claim["claim_id"]],
        },
    )

    assert verified.status_code == 200, verified.text
    body = verified.json()
    assert body["verified"] == 1
    assert body["items"][0]["external_id"] == f"V-{claim['claim_id']}"
    stored = client.get(
        f"/v1/expense/claims/{claim['claim_id']}",
        params={"tenant_id": "tenant-ledger"},
    ).json()
    verification = stored["metadata"]["last_writeback_verification"]
    assert verification["status"] == "verified"
    assert verification["external_status"] == "posted"
    assert connector.calls[-1]["action"] == "ledger.lookup"
    audit = client.get(
        "/v1/audit",
        params={"tenant_id": "tenant-ledger", "resource_id": claim["claim_id"]},
    ).json()["events"]
    assert any(event["action"] == "expense.ledger.verification_verified" for event in audit)
    pending = asyncio.run(container.outbox_store.fetch_pending())
    assert any(event.event_type == "expense.ledger.verification_verified.v1" for event in pending)

    exported = client.get(
        "/v1/expense/ledger/export",
        params={"tenant_id": "tenant-ledger", "format": "json"},
    ).json()["claims"]
    assert exported[0]["verification_status"] == "verified"


def test_external_voucher_verification_detects_amount_mismatch() -> None:
    """验证外部凭证核验金额不一致对应的测试场景。"""
    client, connector, _ = _client_and_connector()
    claim = _approved_claim(client, "voucher-verification-mismatch", amount_cents=5000)
    _writeback_claim(client, claim)
    connector.lookup_amount_override = 4900

    verification = client.post(
        "/v1/expense/ledger/writebacks/verify",
        json={
            "tenant_id": "tenant-ledger",
            "connector_id": "erp-ledger",
            "actor_id": "ledger-writer-user",
            "claim_ids": [claim["claim_id"]],
        },
    )

    assert verification.status_code == 200
    assert verification.json()["mismatch"] == 1
    assert verification.json()["items"][0]["external_amount_cents"] == 4900
    reconciliation = client.get(
        "/v1/expense/ledger/reconciliation",
        params={"tenant_id": "tenant-ledger"},
    ).json()
    assert any(issue["status"] == "verification_mismatch" for issue in reconciliation["issues"])


def test_external_voucher_compensation_is_idempotent_and_reconciled() -> None:
    """验证外部凭证补偿是否幂等及已核对对应的测试场景。"""
    client, connector, container = _client_and_connector()
    claim = _approved_claim(client, "voucher-compensation", amount_cents=3200)
    _writeback_claim(client, claim)
    payload = {
        "tenant_id": "tenant-ledger",
        "connector_id": "erp-ledger",
        "actor_id": "ledger-writer-user",
        "claim_ids": [claim["claim_id"]],
        "reason": "duplicate reimbursement discovered",
    }

    first = client.post("/v1/expense/ledger/writebacks/compensate", json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["succeeded"] == 1
    assert first.json()["items"][0]["compensation_id"] == f"C-V-{claim['claim_id']}"
    stored = client.get(
        f"/v1/expense/claims/{claim['claim_id']}",
        params={"tenant_id": "tenant-ledger"},
    ).json()
    writeback = stored["metadata"]["writebacks"]["erp-ledger:ledger.post"]
    assert writeback["status"] == "compensated"
    assert writeback["compensation_reason"] == "duplicate reimbursement discovered"

    replay = client.post("/v1/expense/ledger/writebacks/compensate", json=payload)
    assert replay.status_code == 200
    assert replay.json()["skipped"] == 1
    assert len(connector.compensation_calls) == 1
    reconciliation = client.get(
        "/v1/expense/ledger/reconciliation",
        params={"tenant_id": "tenant-ledger"},
    ).json()
    assert reconciliation["compensated_claims"] == 1
    assert reconciliation["compensated_amount_cents"] == 3200
    assert reconciliation["written_claims"] == 0
    audit = client.get(
        "/v1/audit",
        params={"tenant_id": "tenant-ledger", "resource_id": claim["claim_id"]},
    ).json()["events"]
    assert any(event["action"] == "expense.ledger.compensation_succeeded" for event in audit)
    pending = asyncio.run(container.outbox_store.fetch_pending())
    assert any(event.event_type == "expense.ledger.compensation_succeeded.v1" for event in pending)


def test_failed_external_compensation_can_be_retried() -> None:
    """验证失败外部补偿可以为已重试对应的测试场景。"""
    client, connector, _ = _client_and_connector()
    claim = _approved_claim(client, "voucher-compensation-retry")
    _writeback_claim(client, claim)
    connector.fail_compensation = True
    payload = {
        "tenant_id": "tenant-ledger",
        "connector_id": "erp-ledger",
        "actor_id": "ledger-writer-user",
        "claim_ids": [claim["claim_id"]],
        "reason": "operator correction",
    }

    failed = client.post("/v1/expense/ledger/writebacks/compensate", json=payload)
    assert failed.status_code == 200
    assert failed.json()["failed"] == 1
    stored = client.get(
        f"/v1/expense/claims/{claim['claim_id']}",
        params={"tenant_id": "tenant-ledger"},
    ).json()
    assert stored["metadata"]["writebacks"]["erp-ledger:ledger.post"]["status"] == "succeeded"
    assert stored["metadata"]["last_compensation"]["status"] == "failed"

    connector.fail_compensation = False
    retried = client.post("/v1/expense/ledger/writebacks/compensate", json=payload)
    assert retried.status_code == 200
    assert retried.json()["succeeded"] == 1
    assert len(connector.compensation_calls) == 2


def test_external_verification_and_compensation_require_permission() -> None:
    """验证外部核验及补偿要求权限对应的测试场景。"""
    client, connector, _ = _client_and_connector(ledger_permission=False)
    claim = _approved_claim(client, "voucher-verification-denied")
    base = {
        "tenant_id": "tenant-ledger",
        "connector_id": "erp-ledger",
        "actor_id": "ledger-writer-user",
        "claim_ids": [claim["claim_id"]],
    }

    verify = client.post("/v1/expense/ledger/writebacks/verify", json=base)
    compensate = client.post(
        "/v1/expense/ledger/writebacks/compensate",
        json={**base, "reason": "operator correction"},
    )

    assert verify.status_code == 403
    assert compensate.status_code == 403
    assert connector.calls == []
    assert connector.compensation_calls == []


@pytest.mark.asyncio
async def test_sqlalchemy_writeback_job_round_trip() -> None:
    """验证SQLAlchemy写回任务轮次往返对应的测试场景。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repository = SQLAlchemyExpenseWritebackJobRepository(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    job = ExpenseWritebackJob(
        job_id="writeback-job-sql",
        tenant_id="tenant-ledger",
        connector_id="erp-ledger",
        action="ledger.post",
        actor_id="ledger-writer-user",
        claim_ids=["claim-1"],
        total_claims=1,
        succeeded_claims=1,
        items=[
            ExpenseWritebackItem(
                claim_id="claim-1",
                status=ExpenseWritebackStatus.SUCCEEDED,
                external_id="V-1",
            )
        ],
    )

    await repository.save(job)
    stored = await repository.get("tenant-ledger", job.job_id)

    assert stored is not None
    assert stored.claim_ids == ["claim-1"]
    assert stored.items[0].external_id == "V-1"
    assert [item.job_id for item in await repository.list("tenant-ledger")] == [job.job_id]
    await engine.dispose()
