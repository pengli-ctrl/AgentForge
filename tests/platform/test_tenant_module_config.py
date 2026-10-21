"""测试租户模块配置测试模块。"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.application.tenant_module_service import (
    TenantModuleConfigAccessor,
    TenantModuleConfigError,
    TenantModuleService,
)
from agentforge.platform.infrastructure.memory_tenant_module_repository import (
    MemoryTenantModuleRepository,
)
from agentforge.platform.modules.support.module import SupportModule


def _support_event(tenant_id: str, message_id: str, text: str) -> dict[str, object]:
    """处理客服事件。

    Args:
        tenant_id: 租户 ID，用于数据隔离。
        message_id: 消息 ID。
        text: 待处理文本。

    Returns:
        结构化结果字典。
    """
    return {
        "tenant_id": tenant_id,
        "source": "feishu",
        "message_id": message_id,
        "text": text,
    }


def _put_config(
    client: TestClient,
    tenant_id: str,
    values: dict[str, object],
    *,
    expected_version: int | None = None,
    secret_refs: dict[str, str] | None = None,
) -> object:
    """写入配置。

    Args:
        client: 客户端实例。
        tenant_id: 租户 ID，用于数据隔离。
        values: 字段值集合。
        expected_version: 版本。
        secret_refs: 密钥。

    Returns:
        对象结果。
    """
    body: dict[str, object] = {"values": values, "actor_id": "ops-admin"}
    if expected_version is not None:
        body["expected_version"] = expected_version
    if secret_refs is not None:
        body["secret_refs"] = secret_refs
    return client.put(
        f"/v1/admin/tenants/{tenant_id}/modules/support/config",
        json=body,
    )


def test_tenant_modules_use_distinct_sla_and_routing_configuration() -> None:
    """验证租户模块去重SLA及配置对应的测试场景。"""
    client = TestClient(create_platform_app())

    tenant_a = _put_config(
        client,
        "tenant-enterprise",
        {
            "default_sla_minutes": 30,
            "notification_target": "chat-enterprise",
            "intent_routes": {
                "sales_question": {
                    "assigned_team": "enterprise-sales",
                    "queue": "enterprise-deals",
                    "assignee_id": "ae-1",
                    "sla_minutes": 15,
                    "priority": "p1",
                }
            },
        },
    )
    tenant_b = _put_config(
        client,
        "tenant-smb",
        {
            "default_sla_minutes": 120,
            "notification_target": "chat-smb",
            "intent_routes": {
                "sales_question": {
                    "assigned_team": "smb-sales",
                    "queue": "smb-inbox",
                    "sla_minutes": 90,
                    "priority": "p2",
                }
            },
        },
    )
    assert tenant_a.status_code == 200
    assert tenant_b.status_code == 200

    enterprise = client.post(
        "/v1/support/events/im",
        json=_support_event("tenant-enterprise", "msg-a", "Need a plan price quote"),
    )
    smb = client.post(
        "/v1/support/events/im",
        json=_support_event("tenant-smb", "msg-b", "Need a plan price quote"),
    )
    assert enterprise.status_code == 200
    assert smb.status_code == 200
    enterprise_ticket = enterprise.json()
    smb_ticket = smb.json()

    assert enterprise_ticket["assigned_team"] == "enterprise-sales"
    assert enterprise_ticket["metadata"]["queue"] == "enterprise-deals"
    assert enterprise_ticket["assignee_id"] == "ae-1"
    assert enterprise_ticket["priority"] == "p1"
    assert enterprise_ticket["metadata"]["sla"]["minutes"] == 15
    assert enterprise_ticket["metadata"]["notification_target"] == "chat-enterprise"

    assert smb_ticket["assigned_team"] == "smb-sales"
    assert smb_ticket["metadata"]["queue"] == "smb-inbox"
    assert smb_ticket["priority"] == "p2"
    assert smb_ticket["metadata"]["sla"]["minutes"] == 90
    assert smb_ticket["metadata"]["notification_target"] == "chat-smb"


def test_invalid_config_rolls_back_and_reports_version_conflict() -> None:
    """验证无效配置返回及报告版本冲突对应的测试场景。"""
    client = TestClient(create_platform_app())
    valid = _put_config(
        client,
        "tenant-rollback",
        {"default_sla_minutes": 45, "invoice_gate_team": "finance-a"},
    )
    assert valid.status_code == 200
    assert valid.json()["config_version"] == 2

    invalid = _put_config(
        client,
        "tenant-rollback",
        {"default_sla_minutes": 0},
        expected_version=2,
    )
    assert invalid.status_code == 422

    current = client.get("/v1/admin/tenants/tenant-rollback/modules/support/config")
    assert current.status_code == 200
    assert current.json()["values"]["default_sla_minutes"] == 45
    assert current.json()["values"]["invoice_gate_team"] == "finance-a"
    assert current.json()["config_version"] == 2

    conflict = _put_config(
        client,
        "tenant-rollback",
        {"default_sla_minutes": 60},
        expected_version=1,
    )
    assert conflict.status_code == 409
    unchanged = client.get("/v1/admin/tenants/tenant-rollback/modules/support/config")
    assert unchanged.json()["values"]["default_sla_minutes"] == 45


def test_config_change_is_audited_and_emitted_to_outbox_without_secrets() -> None:
    """验证配置是否已审计及到Outbox不包含密钥对应的测试场景。"""
    app = create_platform_app()
    client = TestClient(app)
    response = _put_config(
        client,
        "tenant-audit",
        {"default_sla_minutes": 25},
        secret_refs={"webhook_signing_key": "vault://agentforge/support/webhook"},
    )
    assert response.status_code == 200
    assert response.json()["secret_refs"] == {
        "webhook_signing_key": "vault://agentforge/support/webhook"
    }
    assert "webhook_signing_key" not in response.json()["values"]

    audit = client.get(
        "/v1/audit",
        params={"tenant_id": "tenant-audit", "resource_id": "support"},
    )
    assert audit.status_code == 200
    actions = [event["action"] for event in audit.json()["events"]]
    assert "tenant.module.config_updated" in actions

    async def read_outbox() -> list[dict]:
        """读取Outbox。

        Returns:
            结果列表。
        """
        summaries, _ = await app.state.container.outbox_store.list_events(
            tenant_id="tenant-audit", limit=20
        )
        result: list[dict] = []
        for summary in summaries:
            detail = await app.state.container.outbox_store.get_event(
                "tenant-audit", summary["event_id"]
            )
            if detail is not None:
                result.append(detail)
        return result

    events = asyncio.run(read_outbox())
    assert any(
        event["event_type"] == "platform.tenant_module.config_changed.v1"
        and event["payload"]["module_name"] == "support"
        for event in events
    )

    plaintext = _put_config(
        client,
        "tenant-audit",
        {"webhook_api_token": "should-not-be-stored"},
        expected_version=2,
    )
    assert plaintext.status_code == 422


def test_deployment_defaults_remain_available_and_modules_are_isolated() -> None:
    """验证默认项可用及模块为隔离对应的测试场景。"""
    client = TestClient(create_platform_app())
    default_config = client.get("/v1/admin/tenants/private-a/modules/support/config")
    assert default_config.status_code == 200
    assert default_config.json()["source"] == "deployment_default"
    assert default_config.json()["has_tenant_override"] is False
    assert default_config.json()["values"]["default_sla_minutes"] == 480

    disabled = client.put(
        "/v1/admin/tenants/private-a/modules/support",
        json={"enabled": False, "actor_id": "ops-admin"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    claim = client.post(
        "/v1/expense/claims",
        json={
            "tenant_id": "private-a",
            "applicant_id": "employee-1",
            "amount_cents": 1200,
            "expense_date": "2026-10-19",
            "category": "meal",
            "idempotency_key": "private-a-expense",
        },
    )
    assert claim.status_code == 200


@pytest.mark.asyncio
async def test_module_config_accessor_is_scoped_to_one_module() -> None:
    """验证模块配置是否按范围隔离到单个模块对应的测试场景。"""
    service = TenantModuleService(MemoryTenantModuleRepository())
    service.register_module(SupportModule.manifest)
    support_config = TenantModuleConfigAccessor(service, "support")

    values = await support_config.effective_values("tenant-scope")
    assert values["default_sla_minutes"] == 480
    assert not hasattr(support_config, "effective_config")
    with pytest.raises(TenantModuleConfigError, match="not deployed"):
        await TenantModuleConfigAccessor(service, "expense").effective_values("tenant-scope")
