from __future__ import annotations

import hashlib
import json
from typing import Any


class FeishuSignatureVerifier:
    def __init__(self, encrypt_key: str) -> None:
        self._encrypt_key = encrypt_key

    def verify(self, timestamp: str, nonce: str, body: bytes, signature: str) -> bool:
        if not all((timestamp, nonce, signature)):
            return False
        payload = timestamp + nonce + self._encrypt_key + body.decode("utf-8")
        expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return expected == signature


class FeishuEventParser:
    def parse(self, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = payload.get("event") or {}
        message = event.get("message") or {}
        sender = event.get("sender") or {}
        sender_id = sender.get("sender_id") or {}
        content = self._parse_content(message.get("content"))
        return {
            "tenant_id": tenant_id,
            "source": "feishu",
            "message_id": message.get("message_id", ""),
            "conversation_id": message.get("chat_id", ""),
            "customer_id": sender_id.get("open_id", ""),
            "text": content,
        }

    @staticmethod
    def _parse_content(raw_content: Any) -> str:
        if isinstance(raw_content, dict):
            return str(raw_content.get("text", "")).strip()
        if not isinstance(raw_content, str):
            return ""
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
            return raw_content.strip()
        return str(parsed.get("text", "")).strip()
