"""安全模块。"""

from __future__ import annotations

import hashlib
import hmac


def verify_event_hmac(raw_body: bytes, secret: str, provided: str) -> bool:
    """校验事件。

    Args:
        raw_body: 请求体。
        secret: 密钥。
        provided: 输入参数。

    Returns:
        操作是否成功。
    """
    if not secret:
        return True
    if not provided:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)
