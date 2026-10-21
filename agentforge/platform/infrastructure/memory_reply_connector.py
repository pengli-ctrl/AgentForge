"""记忆回复连接器模块。"""

from __future__ import annotations


class MemoryReplyConnector:
    """回复连接器实现。"""

    def __init__(self) -> None:
        """初始化 MemoryReplyConnector。"""
        self.messages: list[dict[str, str]] = []

    async def send_text(self, target: str, text: str, idempotency_key: str) -> dict:
        """发送文本。

        Args:
            target: 操作目标。
            text: 待处理文本。
            idempotency_key: 幂等键，用于避免重复处理。

        Returns:
            结构化结果字典。
        """
        self.messages.append(
            {
                "target": target,
                "text": text,
                "idempotency_key": idempotency_key,
            }
        )
        return {"message_id": f"mem-{len(self.messages)}"}
