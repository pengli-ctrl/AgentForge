"""记忆附件仓储模块。"""

from __future__ import annotations

from copy import deepcopy

from agentforge.platform.modules.expense.domain.attachment import ExpenseAttachment


class MemoryExpenseAttachmentRepository:
    """报销附件仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryExpenseAttachmentRepository。"""
        self._attachments: dict[str, ExpenseAttachment] = {}

    async def save(self, attachment: ExpenseAttachment) -> None:
        """保存报销附件。

        Args:
            attachment: 附件。
        """
        self._attachments[attachment.attachment_id] = deepcopy(attachment)

    async def get(self, tenant_id: str, attachment_id: str) -> ExpenseAttachment | None:
        """读取报销附件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            attachment_id: 附件 ID。

        Returns:
            报销附件无结果。
        """
        attachment = self._attachments.get(attachment_id)
        if attachment is None or attachment.tenant_id != tenant_id:
            return None
        return deepcopy(attachment)

    async def list_by_ids(
        self, tenant_id: str, attachment_ids: list[str]
    ) -> list[ExpenseAttachment]:
        """查询由。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            attachment_ids: 附件 ID 列表。

        Returns:
            结果列表。
        """
        attachments: list[ExpenseAttachment] = []
        for attachment_id in attachment_ids:
            attachment = self._attachments.get(attachment_id)
            if attachment is not None and attachment.tenant_id == tenant_id:
                attachments.append(deepcopy(attachment))
        return attachments
