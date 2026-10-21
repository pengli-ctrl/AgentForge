"""端口模块。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from agentforge.platform.domain.authorization import AuthorizationDecision
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.modules.support.domain.ticket import Ticket


class TicketRepository(Protocol):
    """工单仓储，负责持久化读写。"""

    async def get(self, tenant_id: str, ticket_id: str) -> Ticket | None:
        """读取工单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            ticket_id: 工单 ID。

        Returns:
            工单无结果。
        """
        ...

    async def save(
        self,
        ticket: Ticket,
        events: list[EventEnvelope] | None = None,
    ) -> Ticket:
        """保存工单。

        Args:
            ticket: 客服工单对象。
            events: 事件。

        Returns:
            工单结果。
        """
        ...

    async def get_by_idempotency_key(self, tenant_id: str, idempotency_key: str) -> Ticket | None:
        """获取由键。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            idempotency_key: 幂等键，用于避免重复处理。

        Returns:
            工单无结果。
        """
        ...

    async def list(
        self,
        tenant_id: str,
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
        assigned_team: str | None = None,
        assignee_id: str | None = None,
        queue: str | None = None,
        overdue: bool = False,
        due_before: str | None = None,
    ) -> tuple[list[Ticket], str | None]:
        """查询工单。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            status: 目标状态。
            limit: 返回记录的最大数量。
            cursor: 分页游标。
            assigned_team: 输入参数。
            assignee_id: 处理人 ID。
            queue: 队列。
            overdue: 逾期。
            due_before: 到期之前。

        Returns:
            结果元组。
        """
        ...

    async def list_all(self, limit: int = 10_000) -> Sequence[Ticket]:
        """查询全部。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...


class NotificationPort(Protocol):
    """通知能力端口协议。"""

    async def send(
        self,
        *,
        tenant_id: str,
        ticket_id: str,
        event_type: str,
        idempotency_key: str,
        text: str,
        payload: dict[str, object],
        target: str | None = None,
    ) -> dict[str, object]:
        """发送通知。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            ticket_id: 工单 ID。
            event_type: 事件类型。
            idempotency_key: 幂等键，用于避免重复处理。
            text: 待处理文本。
            payload: 事件、工作流或请求载荷。
            target: 操作目标。

        Returns:
            结构化结果字典。
        """
        ...


class ReplyConnectorPort(Protocol):
    """回复能力端口协议。"""

    async def send_text(
        self,
        target: str,
        text: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        """发送回复文本。

        Args:
            target: 操作目标。
            text: 待处理文本。
            idempotency_key: 幂等键，用于避免重复处理。

        Returns:
            结构化结果字典。
        """
        ...


class HighRiskAuthorizerPort(Protocol):
    """高风险授权器能力端口协议。"""

    async def authorize(
        self,
        *,
        tenant_id: str,
        principal: str,
        action: str,
        resource_type: str,
        resource_id: str,
        ticket: Ticket | None = None,
    ) -> AuthorizationDecision:
        """判断高风险动作是否允许执行。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            principal: 当前认证主体。
            action: 待执行动作名称。
            resource_type: 资源类型。
            resource_id: 资源 ID。
            ticket: 客服工单对象。

        Returns:
            决策结果。
        """
        ...
