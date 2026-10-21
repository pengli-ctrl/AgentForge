"""记忆通知网关模块。"""

from __future__ import annotations

from copy import deepcopy


class MemoryNotificationGateway:
    """通知网关抽象。"""

    def __init__(self) -> None:
        """初始化 MemoryNotificationGateway。"""
        self.sent: list[dict[str, object]] = []
        self._keys: set[tuple[str, str]] = set()

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
        key = (tenant_id, idempotency_key)
        if key in self._keys:
            return {"delivered": True, "idempotent_replay": True}
        self._keys.add(key)
        self.sent.append(
            deepcopy(
                {
                    "tenant_id": tenant_id,
                    "ticket_id": ticket_id,
                    "event_type": event_type,
                    "idempotency_key": idempotency_key,
                    "text": text,
                    "payload": payload,
                    "target": target,
                }
            )
        )
        return {"delivered": True, "idempotent_replay": False}
