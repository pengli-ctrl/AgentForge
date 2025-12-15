from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class FeishuSignatureVerifier:
    """Verifies Feishu (Lark) event callback signatures under the Encrypt-Key
    strategy.

    Implements the official Feishu/Lark event signature algorithm: the
    signature is the SHA-256 hex digest of ``(timestamp + nonce +
    encrypt_key).encode() + raw_body``. Comparison is constant-time
    (``hmac.compare_digest``). An optional timestamp freshness window
    (``max_age_seconds``) rejects replay of captured callbacks.

    With an empty ``encrypt_key`` no signature can be computed, so
    :meth:`verify` returns ``False`` and callers must treat incoming events as
    *unverified* (and log / handle accordingly) rather than assuming they were
    authenticated.
    """

    def __init__(self, encrypt_key: str, max_age_seconds: float = 0.0) -> None:
        self._encrypt_key = encrypt_key
        self._max_age_seconds = float(max_age_seconds)

    @property
    def configured(self) -> bool:
        """True when an Encrypt-Key is available so signatures can be checked."""
        return bool(self._encrypt_key)

    def verify(
        self,
        timestamp: str,
        nonce: str,
        body: bytes,
        signature: str,
        *,
        now: float | None = None,
    ) -> bool:
        if not self.configured:
            logger.warning("Feishu signature verification skipped: no encrypt_key configured")
            return False
        if not all((timestamp, nonce, body, signature)):
            return False
        if self._max_age_seconds > 0 and not self._within_window(timestamp, now):
            logger.warning("Feishu callback rejected: timestamp outside freshness window")
            return False
        bytes_b1 = (timestamp + nonce + self._encrypt_key).encode("utf-8")
        bytes_b = bytes_b1 + body
        expected = hashlib.sha256(bytes_b).hexdigest()
        return hmac.compare_digest(expected, signature)

    def _within_window(self, timestamp: str, now: float | None) -> bool:
        try:
            ts = int(timestamp)
        except (TypeError, ValueError):
            return False
        current = time.time() if now is None else now
        return current - self._max_age_seconds <= ts <= current + self._max_age_seconds


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
