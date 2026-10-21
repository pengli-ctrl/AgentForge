"""脱敏模块。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|credential|authorization)",
    re.IGNORECASE,
)
_EMAIL = re.compile(
    r"(?<![A-Za-z0-9])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+" r"\.[A-Za-z]{2,}(?![A-Za-z0-9])"
)
_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
_ID_CARD = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)


def redact_text(value: str) -> str:
    """脱敏文本。

    Args:
        value: 待处理值。

    Returns:
        字符串结果。
    """
    redacted = _BEARER.sub("Bearer " + REDACTED, value)
    redacted = _EMAIL.sub(REDACTED, redacted)
    redacted = _PHONE.sub(REDACTED, redacted)
    return _ID_CARD.sub(REDACTED, redacted)


def redact_sensitive(value: Any, *, key: str = "") -> Any:
    """脱敏数据。

    Args:
        value: 待处理值。
        key: 缓存或配置键。

    Returns:
        处理结果对象。
    """
    if key and _SENSITIVE_KEY.search(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {str(k): redact_sensitive(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value


__all__ = ["REDACTED", "redact_sensitive", "redact_text"]
