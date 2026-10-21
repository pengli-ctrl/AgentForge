"""记忆Outbox存储模块。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from agentforge.platform.domain.events import EventEnvelope


@dataclass
class _OutboxEntry:
    """Outbox条目相关组件。

    Attributes:
        event: 待处理事件。
        status: 当前状态。
        attempts: 字段值。
        last_error: 错误。
        published_at: 已发布于。
    """

    event: EventEnvelope
    status: str
    attempts: int = 0
    last_error: str | None = None
    published_at: str | None = None


class MemoryOutboxStore:
    """Outbox相关组件。"""

    def __init__(self) -> None:
        """初始化 MemoryOutboxStore。"""
        self._entries: dict[str, _OutboxEntry] = {}
        self._handler_receipts: dict[tuple[str, str], dict[str, object]] = {}

    async def enqueue(self, event: EventEnvelope) -> None:
        """写入队列Outbox。

        Args:
            event: 待处理事件。
        """
        if event.event_id in self._entries:
            return
        self._entries[event.event_id] = _OutboxEntry(event=event, status="pending")

    async def claim_handler(
        self,
        event_id: str,
        handler_name: str,
        *,
        lease_seconds: int = 60,
    ) -> str:
        """处理报销单处理器。

        Args:
            event_id: 事件 ID。
            handler_name: 处理器名称。
            lease_seconds: 输入参数。

        Returns:
            字符串结果。
        """
        key = (event_id, handler_name)
        now = datetime.now(timezone.utc)
        receipt = self._handler_receipts.get(key)
        if receipt is not None and receipt["status"] == "completed":
            return "completed"
        if receipt is not None and receipt["status"] == "processing":
            claimed_at = receipt["claimed_at"]
            if isinstance(claimed_at, datetime) and claimed_at > now - timedelta(
                seconds=lease_seconds
            ):
                return "busy"
        self._handler_receipts[key] = {
            "status": "processing",
            "claimed_at": now,
            "processed_at": None,
            "last_error": None,
        }
        return "claimed"

    async def complete_handler(self, event_id: str, handler_name: str) -> None:
        """完成处理器。

        Args:
            event_id: 事件 ID。
            handler_name: 处理器名称。
        """
        key = (event_id, handler_name)
        if key in self._handler_receipts:
            self._handler_receipts[key]["status"] = "completed"
            self._handler_receipts[key]["processed_at"] = datetime.now(timezone.utc)

    async def release_handler(self, event_id: str, handler_name: str, error: str = "") -> None:
        """处理释放处理器。

        Args:
            event_id: 事件 ID。
            handler_name: 处理器名称。
            error: 错误。
        """
        key = (event_id, handler_name)
        if error:
            receipt = self._handler_receipts.get(key)
            if receipt is not None:
                receipt["status"] = "failed"
                receipt["last_error"] = error[:2000]
        else:
            self._handler_receipts.pop(key, None)

    async def fetch_pending(self, limit: int = 100) -> list[EventEnvelope]:
        """获取待处理。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        pending = [e.event for e in self._entries.values() if e.status == "pending"][:limit]
        return pending

    async def mark_published(self, event_id: str) -> None:
        """标记已发布。

        Args:
            event_id: 事件 ID。
        """
        entry = self._entries.get(event_id)
        if entry is None:
            return
        entry.status = "published"
        entry.attempts += 0
        entry.published_at = entry.event.occurred_at.isoformat()

    async def mark_failed(self, event_id: str, error: str) -> None:
        """标记失败。

        Args:
            event_id: 事件 ID。
            error: 错误。
        """
        entry = self._entries.get(event_id)
        if entry is None:
            return
        entry.attempts += 1
        entry.last_error = error[:2000]

    async def list_failed(self, limit: int = 100) -> list[dict]:
        """查询失败。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
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
        """查询事件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            status: 目标状态。
            limit: 返回记录的最大数量。
            cursor: 分页游标。

        Returns:
            结果元组。
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
        """读取事件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            event_id: 事件 ID。

        Returns:
            结构化结果字典。
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
        """统计事件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        counts = {"pending": 0, "published": 0, "failed": 0, "discarded": 0}
        for entry in self._entries.values():
            if tenant_id is not None and entry.event.tenant_id != tenant_id:
                continue
            if entry.status in counts:
                counts[entry.status] += 1
        return counts

    async def discard(self, tenant_id: str | None, event_id: str) -> bool:
        """判断丢弃是否成立。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            event_id: 事件 ID。

        Returns:
            操作是否成功。
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
        """重放Outbox。

        Args:
            event_id: 事件 ID。

        Returns:
            操作是否成功。
        """
        entry = self._entries.get(event_id)
        if entry is None:
            return False
        entry.status = "pending"
        entry.attempts = 0
        entry.last_error = None
        for key in [key for key in self._handler_receipts if key[0] == event_id]:
            del self._handler_receipts[key]
        return True

    @staticmethod
    def _summary(entry: _OutboxEntry) -> dict:
        """汇总Outbox信息。

        Args:
            entry: 条目。

        Returns:
            结构化结果字典。
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
