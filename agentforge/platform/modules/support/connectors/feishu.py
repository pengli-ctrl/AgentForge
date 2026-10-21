"""飞书模块。"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class FeishuSignatureVerifier:
    """飞书签名核验器相关组件。"""

    def __init__(self, encrypt_key: str, max_age_seconds: float = 0.0) -> None:
        """初始化 FeishuSignatureVerifier。

        Args:
            encrypt_key: 键。
            max_age_seconds: 最大。
        """
        self._encrypt_key = encrypt_key
        self._max_age_seconds = float(max_age_seconds)

    @property
    def configured(self) -> bool:
        """返回已配置。

        Returns:
            操作是否成功。
        """
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
        """校验飞书签名核验器。

        Args:
            timestamp: 输入参数。
            nonce: 输入参数。
            body: 请求体数据。
            signature: 签名。
            now: 输入参数。

        Returns:
            操作是否成功。
        """
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
        """判断窗口是否成立。

        Args:
            timestamp: 输入参数。
            now: 输入参数。

        Returns:
            操作是否成功。
        """
        try:
            ts = int(timestamp)
        except (TypeError, ValueError):
            return False
        current = time.time() if now is None else now
        return current - self._max_age_seconds <= ts <= current + self._max_age_seconds


class FeishuEventParser:
    """飞书事件解析器相关组件。"""

    def parse(self, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """解析飞书事件解析器。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            payload: 事件、工作流或请求载荷。

        Returns:
            结构化结果字典。
        """
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
        """解析内容。

        Args:
            raw_content: 内容。

        Returns:
            字符串结果。
        """
        if isinstance(raw_content, dict):
            return str(raw_content.get("text", "")).strip()
        if not isinstance(raw_content, str):
            return ""
        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
            return raw_content.strip()
        return str(parsed.get("text", "")).strip()
