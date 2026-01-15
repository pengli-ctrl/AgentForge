"""AgentForge 平台连接器层：feishu。

本模块负责 feishu 相关的平台能力，是 平台连接器层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：FeishuSignatureVerifier、FeishuEventParser。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class FeishuSignatureVerifier:
    """FeishuSignatureVerifier。

    FeishuSignatureVerifier 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 configured()。
    - 方法 verify()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, encrypt_key: str, max_age_seconds: float = 0.0) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            encrypt_key: str，调用方传入的 encrypt_key 参数。
            max_age_seconds: float，调用方传入的 max_age_seconds 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._encrypt_key = encrypt_key
        self._max_age_seconds = float(max_age_seconds)

    @property
    def configured(self) -> bool:
        """执行 configured 对应的逻辑，并返回处理结果。

        Returns:
            bool，函数执行后的结果。
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
        """执行 verify 对应的逻辑，并返回处理结果。

        Args:
            timestamp: str，调用方传入的 timestamp 参数。
            nonce: str，调用方传入的 nonce 参数。
            body: bytes，调用方传入的 body 参数。
            signature: str，调用方传入的 signature 参数。
            now: float | None，调用方传入的 now 参数。

        Returns:
            bool，函数执行后的结果。
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
        """执行 _within_window 对应的逻辑，并返回处理结果。

        Args:
            timestamp: str，调用方传入的 timestamp 参数。
            now: float | None，调用方传入的 now 参数。

        Returns:
            bool，函数执行后的结果。
        """
        try:
            ts = int(timestamp)
        except (TypeError, ValueError):
            return False
        current = time.time() if now is None else now
        return current - self._max_age_seconds <= ts <= current + self._max_age_seconds


class FeishuEventParser:
    """FeishuEventParser。

    FeishuEventParser 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - 方法 parse()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def parse(self, tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """执行 parse 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            payload: dict[str, Any]，调用方传入的 payload 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。
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
        """执行 _parse_content 对应的逻辑，并返回处理结果。

        Args:
            raw_content: Any，调用方传入的 raw_content 参数。

        Returns:
            str，函数执行后的结果。
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
