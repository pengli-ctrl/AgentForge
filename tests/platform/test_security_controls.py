"""测试安全测试模块。"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.modules.expense.application.attachment_service import (
    ExpenseAttachmentService,
)
from agentforge.platform.modules.expense.infrastructure.memory_attachment_repository import (
    MemoryExpenseAttachmentRepository,
)
from agentforge.platform.runtime import build_memory_container
from agentforge.platform.security.lifecycle import DataLifecycleError, TenantDataLifecycleService
from agentforge.platform.security.oidc import (
    OIDCAuthenticationError,
    OIDCPrincipal,
    StaticOIDCProvider,
    authorize_principal,
    bearer_token,
)
from agentforge.platform.security.redaction import REDACTED, redact_sensitive, redact_text
from agentforge.platform.security.secrets import (
    AwsKmsSecretProvider,
    EnvironmentSecretProvider,
    SecretResolver,
    SecretValue,
    VaultSecretProvider,
)


@pytest.mark.asyncio
async def test_environment_secret_resolution_rotation_and_safe_repr() -> None:
    """验证环境密钥解析及安全表示对应的测试场景。"""
    environment = {"WEBHOOK_SECRET": "initial-secret"}
    provider = EnvironmentSecretProvider(environment)
    resolver = SecretResolver({"env": provider})

    resolved = await resolver.resolve("env://WEBHOOK_SECRET")
    rotated = await resolver.rotate("env://WEBHOOK_SECRET", "rotated-secret")

    assert resolved.reveal() == "initial-secret"
    assert rotated.reveal() == "rotated-secret"
    assert rotated.version != resolved.version
    assert "initial-secret" not in str(resolved)
    assert "rotated-secret" not in repr(rotated)
    assert isinstance(resolved, SecretValue)


@pytest.mark.asyncio
async def test_vault_and_kms_reference_providers() -> None:
    """验证密钥库及KMS参考提供方对应的测试场景。"""
    requests: list[httpx.Request] = []

    def vault_handler(request: httpx.Request) -> httpx.Response:
        """处理密钥库处理器。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            响应结果。
        """
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"data": {"data": {"token": "vault-value"}}})
        return httpx.Response(204)

    vault_client = httpx.AsyncClient(
        transport=httpx.MockTransport(vault_handler), base_url="http://vault"
    )
    vault = VaultSecretProvider("http://vault", "root-token", client=vault_client)
    resolved = await vault.resolve("vault://agentforge/support#token")
    rotated = await vault.rotate("vault://agentforge/support#token", "new-vault-value")
    assert resolved.reveal() == "vault-value"
    assert rotated.reveal() == "new-vault-value"
    assert requests[0].headers["X-Vault-Token"] == "root-token"
    await vault_client.aclose()

    class FakeKms:
        """用于测试的模拟密钥管理服务。"""

        def decrypt(self, *, CiphertextBlob: bytes) -> dict[str, bytes]:
            """解密受保护的数据。

            Args:
                CiphertextBlob: 输入参数。

            Returns:
                结构化结果字典。
            """
            assert CiphertextBlob == b"ciphertext"
            return {"Plaintext": b"kms-value"}

    kms_ref = "kms://" + base64.b64encode(b"ciphertext").decode("ascii")
    kms_value = await AwsKmsSecretProvider(FakeKms()).resolve(kms_ref)
    assert kms_value.reveal() == "kms-value"
    assert "kms-value" not in str(kms_value)


@pytest.mark.asyncio
async def test_oidc_extension_point_and_tenant_permission_checks() -> None:
    """验证OIDC点及租户权限对应的测试场景。"""
    principal = OIDCPrincipal(
        tenant_id="tenant-sso",
        subject="user-1",
        issuer="https://idp.example.com",
        roles=frozenset({"support"}),
        permissions=frozenset({"support.ticket.read"}),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    provider = StaticOIDCProvider({"valid-token": principal})

    assert bearer_token("Bearer valid-token") == "valid-token"
    authenticated = await provider.authenticate("valid-token")
    authorize_principal(authenticated, "tenant-sso", "support.ticket.read")
    with pytest.raises(OIDCAuthenticationError):
        authorize_principal(authenticated, "tenant-other")
    with pytest.raises(OIDCAuthenticationError):
        authorize_principal(authenticated, "tenant-sso", "support.ticket.approve")

    expired = OIDCPrincipal(
        tenant_id="tenant-sso",
        subject="user-2",
        issuer="https://idp.example.com",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    with pytest.raises(OIDCAuthenticationError):
        await StaticOIDCProvider({"expired": expired}).authenticate("expired")


def test_output_redaction_removes_secrets_and_common_pii() -> None:
    """验证输出密钥及公共PII对应的测试场景。"""
    payload = {
        "email": "person@example.com",
        "phone": "13800138000",
        "id_card": "110101199001011234",
        "authorization": "Bearer abc.def.ghi",
        "nested": {"api_key": "plain-secret", "message": "contact person@example.com"},
    }
    redacted = redact_sensitive(payload)
    assert redacted["authorization"] == REDACTED
    assert redacted["nested"]["api_key"] == REDACTED
    assert redacted["email"] == REDACTED
    assert redacted["phone"] == REDACTED
    assert redacted["id_card"] == REDACTED
    assert "person@example.com" not in redact_text("contact person@example.com")


@pytest.mark.asyncio
async def test_tenant_data_lifecycle_runs_erasers_and_audits() -> None:
    """验证租户数据生命周期运行记录及审计对应的测试场景。"""
    container = build_memory_container()
    service = TenantDataLifecycleService(container.audit_repository, container.outbox_store)
    erased: list[str] = []

    async def ticket_eraser(tenant_id: str) -> dict[str, int]:
        """处理工单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        erased.append(tenant_id)
        return {"tickets": 3, "attachments": 2}

    service.register_eraser("support", ticket_eraser)
    result = await service.erase_tenant(
        tenant_id="tenant-delete",
        actor_id="privacy-admin",
        reason="customer request",
        confirmation="tenant-delete",
    )
    assert result["erased"] == {"support.tickets": 3, "support.attachments": 2}
    assert erased == ["tenant-delete"]
    events = await container.audit_repository.list_events("tenant-delete")
    assert events[0].action == "tenant.data.erased"
    with pytest.raises(DataLifecycleError, match="confirmation"):
        await service.erase_tenant(
            tenant_id="tenant-delete",
            actor_id="privacy-admin",
            reason="bad confirmation",
            confirmation="wrong",
        )


def test_audit_export_redacts_and_retention_purges_tenant_only() -> None:
    """验证审计导出及保留租户对应的测试场景。"""
    container = build_memory_container()
    repository = container.audit_repository
    now = datetime.now(timezone.utc)
    assert repository is not None

    import asyncio

    async def seed() -> None:
        """初始化初始数据。"""
        await repository.save(
            AuditEvent(
                event_id="audit-pii",
                tenant_id="tenant-a",
                action="ticket.created",
                resource_type="ticket",
                resource_id="ticket-1",
                actor_id="agent-1",
                payload={"email": "person@example.com", "api_key": "plain-secret"},
                occurred_at=now - timedelta(days=2),
            )
        )
        await repository.save(
            AuditEvent(
                event_id="audit-other",
                tenant_id="tenant-b",
                action="ticket.created",
                resource_type="ticket",
                resource_id="ticket-2",
                actor_id="agent-1",
                payload={"email": "other@example.com"},
                occurred_at=now - timedelta(days=2),
            )
        )

    asyncio.run(seed())
    client = TestClient(create_platform_app(container))

    exported = client.get(
        "/v1/audit/export",
        params={"tenant_id": "tenant-a", "format": "json"},
    )
    assert exported.status_code == 200
    assert "person@example.com" not in exported.text
    assert "plain-secret" not in exported.text
    assert REDACTED in exported.text

    csv_export = client.get(
        "/v1/audit/export",
        params={"tenant_id": "tenant-a", "format": "csv"},
    )
    assert csv_export.status_code == 200
    assert "text/csv" in csv_export.headers["content-type"]

    purge = client.post(
        "/v1/audit/retention/purge",
        json={
            "tenant_id": "tenant-a",
            "actor_id": "privacy-admin",
            "confirmation": "tenant-a",
            "before": (now + timedelta(minutes=1)).isoformat(),
        },
    )
    assert purge.status_code == 200
    assert purge.json()["deleted"] == 1

    tenant_a = client.get("/v1/audit", params={"tenant_id": "tenant-a"}).json()["events"]
    tenant_b = client.get("/v1/audit", params={"tenant_id": "tenant-b"}).json()["events"]
    assert [event["action"] for event in tenant_a] == ["audit.retention.purged"]
    assert [event["event_id"] for event in tenant_b] == ["audit-other"]


@pytest.mark.asyncio
async def test_attachment_download_url_uses_bounded_expiry() -> None:
    """验证附件下载URL使用对应的测试场景。"""
    repository = MemoryExpenseAttachmentRepository()
    store = type("Store", (), {})()
    store.objects = {}

    async def put(key, data, content_type=""):
        """写入记录。

        Args:
            key: 缓存或配置键。
            data: 待处理数据。
            content_type: 内容 MIME 类型。
        """
        store.objects[key] = data

    async def presigned(key, expires_seconds=300):
        """处理预签名。

        Args:
            key: 缓存或配置键。
            expires_seconds: 输入参数。

        Returns:
            处理结果。
        """
        assert expires_seconds == 120
        return f"memory://{key}?expires={expires_seconds}"

    store.put = put
    store.presigned_get_url = presigned
    service = ExpenseAttachmentService(
        repository,
        store,
        download_url_ttl_seconds=120,
    )
    attachment = await service.upload(
        tenant_id="tenant-files",
        filename="proof.txt",
        content_type="text/plain",
        data=b"proof",
    )
    loaded = await service.get("tenant-files", attachment.attachment_id)
    assert loaded is not None
    assert loaded[1].endswith("expires=120")
    with pytest.raises(ValueError):
        ExpenseAttachmentService(repository, store, download_url_ttl_seconds=3601)
