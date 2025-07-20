from __future__ import annotations


class MemoryReplyConnector:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    async def send_text(self, target: str, text: str, idempotency_key: str) -> dict:
        self.messages.append(
            {
                "target": target,
                "text": text,
                "idempotency_key": idempotency_key,
            }
        )
        return {"message_id": f"mem-{len(self.messages)}"}
