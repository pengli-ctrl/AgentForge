"""AgentForge 平台基础设施层：memory_outbox_store。

本模块提供 memory_outbox_store 的内存实现，用于单元测试、本地开发和离线验证。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：_OutboxEntry、MemoryOutboxStore。
"""

from __future__ import annotations

from dataclasses import dataclass

from agentforge.platform.domain.events import EventEnvelope


@dataclass
class _OutboxEntry:
    """_OutboxEntry。

    _OutboxEntry 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - event: EventEnvelope。
    - status: str。
    - attempts: int。
    - last_error: str | None。
    - published_at: str | None。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    event: EventEnvelope
    status: str
    attempts: int = 0
    last_error: str | None = None
    published_at: str | None = None


class MemoryOutboxStore:
    """MemoryOutboxStore。

    MemoryOutboxStore 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 enqueue()。
    - 方法 fetch_pending()。
    - 方法 mark_published()。
    - 方法 mark_failed()。
    - 方法 list_failed()。
    - 方法 list_events()。
    - 方法 get_event()。
    - 方法 count_events()。
    - 方法 discard()。
    - 方法 replay()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._entries: dict[str, _OutboxEntry] = {}

    async def enqueue(self, event: EventEnvelope) -> None:
        """执行 enqueue 对应的逻辑，并返回处理结果。

        Args:
            event: EventEnvelope，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        if event.event_id in self._entries:
            return
        self._entries[event.event_id] = _OutboxEntry(event=event, status="pending")

    async def fetch_pending(self, limit: int = 100) -> list[EventEnvelope]:
        """从外部或内部来源获取数据，并返回调用方需要的结果。

        Args:
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[EventEnvelope]，函数执行后的结果。
        """
        pending = [e.event for e in self._entries.values() if e.status == "pending"][:limit]
        return pending

    async def mark_published(self, event_id: str) -> None:
        """执行 mark_published 对应的逻辑，并返回处理结果。

        Args:
            event_id: str，调用方传入的 event_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        entry = self._entries.get(event_id)
        if entry is None:
            return
        entry.status = "published"
        entry.attempts += 0
        entry.published_at = entry.event.occurred_at.isoformat()

    async def mark_failed(self, event_id: str, error: str) -> None:
        """执行 mark_failed 对应的逻辑，并返回处理结果。

        Args:
            event_id: str，调用方传入的 event_id 参数。
            error: str，调用方传入的 error 参数。

        Returns:
            None，函数执行后的结果。
        """
        entry = self._entries.get(event_id)
        if entry is None:
            return
        entry.attempts += 1
        entry.last_error = error[:2000]

    async def list_failed(self, limit: int = 100) -> list[dict]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[dict]，函数执行后的结果。
        """
        failed = [e for e in self._entries.values() if e.status == "failed"]
        return [self._summary(e) for e in failed[:limit]]

    async def list_events(
        self,
        tenant_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[dict], str | None]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            status: str | None，调用方传入的 status 参数。
            limit: int，调用方传入的 limit 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            tuple[list[dict], str | None]，函数执行后的结果。
        """
        entries = list(self._entries.values())
        entries.sort(key=lambda e: e.event.occurred_at)
        if tenant_id is not None:
            entries = [e for e in entries if e.event.tenant_id == tenant_id]
        if status is not None:
            entries = [e for e in entries if e.status == status]
        start = int(cursor) if (cursor is not None and cursor.isdigit()) else 0
        bucket = entries[start : start + limit]
        next_cursor = str(start + len(bucket)) if start + len(bucket) < len(entries) else None
        return [self._summary(e) for e in bucket], next_cursor

    async def get_event(self, tenant_id: str | None, event_id: str) -> dict | None:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            event_id: str，调用方传入的 event_id 参数。

        Returns:
            dict | None，函数执行后的结果。
        """
        entry = self._entries.get(event_id)
        if entry is None:
            return None
        if tenant_id is not None and entry.event.tenant_id != tenant_id:
            return None
        return {
            "event_id": entry.event.event_id,
            "tenant_id": entry.event.tenant_id,
            "event_type": entry.event.event_type,
            "status": entry.status,
            "attempts": entry.attempts,
            "last_error": entry.last_error,
            "payload": entry.event.payload,
            "created_at": entry.event.occurred_at.isoformat(),
            "published_at": entry.published_at,
        }

    async def count_events(self, tenant_id: str | None = None) -> dict[str, int]:
        """执行 count_events 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。

        Returns:
            dict[str, int]，函数执行后的结果。
        """
        counts = {"pending": 0, "published": 0, "failed": 0, "discarded": 0}
        for entry in self._entries.values():
            if tenant_id is not None and entry.event.tenant_id != tenant_id:
                continue
            if entry.status in counts:
                counts[entry.status] += 1
        return counts

    async def discard(self, tenant_id: str | None, event_id: str) -> bool:
        """执行 discard 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            event_id: str，调用方传入的 event_id 参数。

        Returns:
            bool，函数执行后的结果。
        """
        entry = self._entries.get(event_id)
        if entry is None:
            return False
        if tenant_id is not None and entry.event.tenant_id != tenant_id:
            return False
        entry.status = "discarded"
        if not entry.last_error:
            entry.last_error = "discarded by operator"
        return True

    async def replay(self, event_id: str) -> bool:
        """执行 replay 对应的逻辑，并返回处理结果。

        Args:
            event_id: str，调用方传入的 event_id 参数。

        Returns:
            bool，函数执行后的结果。
        """
        entry = self._entries.get(event_id)
        if entry is None:
            return False
        entry.status = "pending"
        entry.attempts = 0
        entry.last_error = None
        return True

    @staticmethod
    def _summary(entry: _OutboxEntry) -> dict:
        """执行 _summary 对应的逻辑，并返回处理结果。

        Args:
            entry: _OutboxEntry，调用方传入的 entry 参数。

        Returns:
            dict，函数执行后的结果。
        """
        return {
            "event_id": entry.event.event_id,
            "tenant_id": entry.event.tenant_id,
            "event_type": entry.event.event_type,
            "status": entry.status,
            "attempts": entry.attempts,
            "last_error": entry.last_error,
            "created_at": entry.event.occurred_at.isoformat(),
            "published_at": entry.published_at,
        }
