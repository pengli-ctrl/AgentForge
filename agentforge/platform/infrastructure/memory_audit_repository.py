"""记忆审计仓储模块。"""

from __future__ import annotations

from datetime import datetime

from agentforge.platform.domain.audit import AuditEvent


class MemoryAuditRepository:
    """审计仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryAuditRepository。"""
        self.events: list[AuditEvent] = []

    async def save(self, event: AuditEvent) -> None:
        """保存审计。

        Args:
            event: 待处理事件。
        """
        self.events.append(event)

    async def list_events(
        self,
        tenant_id: str,
        limit: int = 100,
        resource_id: str | None = None,
    ) -> list[AuditEvent]:
        """查询事件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。
            resource_id: 资源 ID。

        Returns:
            结果列表。
        """
        events = [
            event
            for event in self.events
            if event.tenant_id == tenant_id
            and (resource_id is None or event.resource_id == resource_id)
        ]
        return sorted(events, key=lambda event: event.occurred_at, reverse=True)[:limit]

    async def delete_events_before(self, tenant_id: str, before: datetime) -> int:
        """删除事件之前。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            before: 之前。

        Returns:
            整数结果。
        """
        original = len(self.events)
        self.events = [
            event
            for event in self.events
            if not (event.tenant_id == tenant_id and event.occurred_at < before)
        ]
        return original - len(self.events)

    async def query_events(
        self,
        tenant_id: str | None = None,
        action: str | None = None,
        actor_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[AuditEvent], str | None]:
        """查询事件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            action: 待执行动作名称。
            actor_id: 执行操作的参与者 ID。
            resource_id: 资源 ID。
            resource_type: 资源类型。
            limit: 返回记录的最大数量。
            cursor: 分页游标。

        Returns:
            结果元组。
        """
        events = [
            event
            for event in self.events
            if (tenant_id is None or event.tenant_id == tenant_id)
            and (action is None or event.action == action)
            and (actor_id is None or event.actor_id == actor_id)
            and (resource_id is None or event.resource_id == resource_id)
            and (resource_type is None or event.resource_type == resource_type)
        ]
        events.sort(key=lambda event: event.occurred_at, reverse=True)
        start = int(cursor) if (cursor is not None and cursor.isdigit()) else 0
        bucket = events[start : start + limit]
        next_cursor = str(start + len(bucket)) if start + len(bucket) < len(events) else None
        return bucket, next_cursor
