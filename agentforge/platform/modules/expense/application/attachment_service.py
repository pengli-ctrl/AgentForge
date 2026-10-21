"""附件服务模块。"""

from __future__ import annotations

import hashlib
from pathlib import PurePath
from uuid import uuid4

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.risk import RiskLevel
from agentforge.platform.domain.usage import UsageMetric
from agentforge.platform.modules.expense.domain.attachment import ExpenseAttachment
from agentforge.platform.modules.expense.ports import ExpenseAttachmentRepository
from agentforge.platform.sdk.ports import AuditPort, ObjectStorePort, UsagePort

_MAX_ATTACHMENT_BYTES = 100 * 1024 * 1024


class ExpenseAttachmentService:
    """报销附件应用服务，编排领域用例及其副作用。"""

    def __init__(
        self,
        repository: ExpenseAttachmentRepository,
        object_store: ObjectStorePort,
        audit: AuditPort | None = None,
        download_url_ttl_seconds: int = 300,
        usage: UsagePort | None = None,
    ) -> None:
        """初始化 ExpenseAttachmentService。

        Args:
            repository: 数据仓储实现。
            object_store: 对象存储。
            audit: 审计。
            download_url_ttl_seconds: 下载URL。
            usage: 用量统计数据。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if download_url_ttl_seconds < 1 or download_url_ttl_seconds > 3600:
            raise ValueError("download_url_ttl_seconds must be between 1 and 3600")
        self._repository = repository
        self._object_store = object_store
        self._audit = audit
        self._download_url_ttl_seconds = download_url_ttl_seconds
        self._usage = usage

    async def upload(
        self,
        *,
        tenant_id: str,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> ExpenseAttachment:
        """上传报销附件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            filename: 输入参数。
            content_type: 内容 MIME 类型。
            data: 待处理数据。

        Returns:
            报销附件结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if not data:
            raise ValueError("attachment content is required")
        if len(data) > _MAX_ATTACHMENT_BYTES:
            raise ValueError("attachment exceeds 100 MB limit")
        content_type = content_type.strip() or "application/octet-stream"
        attachment_id = str(uuid4())
        object_key = f"tenants/{tenant_id}/modules/expense/attachments/{attachment_id}"
        sha256 = hashlib.sha256(data).hexdigest()
        await self._object_store.put(object_key, data, content_type)
        attachment = await self.register_stored_object(
            tenant_id=tenant_id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            sha256=sha256,
            object_key=object_key,
            attachment_id=attachment_id,
        )
        if self._usage is not None:
            await self._usage.record(
                tenant_id=tenant_id,
                metric=UsageMetric.STORAGE_BYTES,
                quantity=len(data),
                source="expense-attachment",
                idempotency_key=f"storage:expense-attachment:{attachment_id}",
                metadata={"content_type": content_type},
            )
        return attachment

    async def register_stored_object(
        self,
        *,
        tenant_id: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
        object_key: str,
        attachment_id: str | None = None,
    ) -> ExpenseAttachment:
        """注册对象。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            filename: 输入参数。
            content_type: 内容 MIME 类型。
            size_bytes: 大小。
            sha256: 输入参数。
            object_key: 对象键。
            attachment_id: 附件 ID。

        Returns:
            报销附件结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if size_bytes < 1:
            raise ValueError("attachment content is required")
        if size_bytes > _MAX_ATTACHMENT_BYTES:
            raise ValueError("attachment exceeds 100 MB limit")
        safe_name = PurePath(filename).name or "attachment"
        content_type = content_type.strip() or "application/octet-stream"
        attachment_id = attachment_id or str(uuid4())
        attachment = ExpenseAttachment(
            attachment_id=attachment_id,
            tenant_id=tenant_id,
            filename=safe_name,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
            object_key=object_key,
        )
        await self._repository.save(attachment)
        await self._audit_event(
            "expense.attachment.uploaded",
            tenant_id,
            attachment_id,
            {"size_bytes": size_bytes, "sha256": sha256},
        )
        return attachment

    async def get(
        self,
        tenant_id: str,
        attachment_id: str,
    ) -> tuple[ExpenseAttachment, str] | None:
        """读取报销附件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            attachment_id: 附件 ID。

        Returns:
            结果元组。
        """
        attachment = await self.get_metadata(tenant_id, attachment_id)
        if attachment is None:
            return None
        url = await self._object_store.presigned_get_url(
            attachment.object_key, self._download_url_ttl_seconds
        )
        return attachment, url

    async def get_metadata(
        self,
        tenant_id: str,
        attachment_id: str,
    ) -> ExpenseAttachment | None:
        """获取元数据。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            attachment_id: 附件 ID。

        Returns:
            报销附件无结果。
        """
        return await self._repository.get(tenant_id, attachment_id)

    async def get_content(self, tenant_id: str, attachment_id: str) -> bytes | None:
        """读取内容。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            attachment_id: 附件 ID。

        Returns:
            无结果。
        """
        attachment = await self._repository.get(tenant_id, attachment_id)
        if attachment is None:
            return None
        return await self._object_store.get(attachment.object_key)

    async def link_to_claim(
        self,
        tenant_id: str,
        attachment_ids: list[str],
        claim_id: str,
    ) -> list[ExpenseAttachment]:
        """关联到报销单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            attachment_ids: 附件 ID 列表。
            claim_id: 报销单 ID。

        Returns:
            结果列表。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        if not attachment_ids:
            return []
        attachments = await self._repository.list_by_ids(tenant_id, attachment_ids)
        if len(attachments) != len(set(attachment_ids)):
            raise ValueError("one or more attachments were not found for tenant")
        linked: list[ExpenseAttachment] = []
        for attachment in attachments:
            if attachment.claim_id not in {None, claim_id}:
                raise ValueError("attachment is already linked to another claim")
            attachment.claim_id = claim_id
            await self._repository.save(attachment)
            linked.append(attachment)
        return linked

    async def _audit_event(
        self,
        action: str,
        tenant_id: str,
        attachment_id: str,
        payload: dict[str, object],
    ) -> None:
        """记录审计结果事件。

        Args:
            action: 待执行动作名称。
            tenant_id: 租户 ID，用于数据隔离。
            attachment_id: 附件 ID。
            payload: 事件、工作流或请求载荷。
        """
        if self._audit is None:
            return
        await self._audit.save(
            AuditEvent(
                event_id=str(uuid4()),
                tenant_id=tenant_id,
                action=action,
                resource_type="expense_attachment",
                resource_id=attachment_id,
                risk_level=RiskLevel.LOW,
                actor_type="user",
                actor_id="system",
                trace_id=str(uuid4()),
                payload=payload,
            )
        )
