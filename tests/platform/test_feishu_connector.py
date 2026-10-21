"""飞书连接器测试模块。

本测试模块验证 test_feishu_connector 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：make_signature、test_feishu_challenge、test_feishu_signed_message_creates_ticket、test_feishu_
    invalid_signature_is_rejected。
"""

import hashlib
import json

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.runtime import build_memory_container


def make_signature(timestamp: str, nonce: str, key: str, body: bytes) -> str:
    """构造签名。

    Args:
        timestamp: 输入参数。
        nonce: 输入参数。
        key: 缓存或配置键。
        body: 请求体数据。

    Returns:
        字符串结果。
    """
    payload = timestamp + nonce + key + body.decode("utf-8")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_feishu_challenge() -> None:
    """验证飞书对应的测试场景。"""
    client = TestClient(
        create_platform_app(build_memory_container(), feishu_verification_token="verify-token")
    )
    response = client.post(
        "/v1/events/feishu?tenant_id=tenant-1",
        json={"type": "url_verification", "token": "verify-token", "challenge": "challenge-1"},
    )
    assert response.status_code == 200
    assert response.json()["challenge"] == "challenge-1"


def test_feishu_signed_message_creates_ticket() -> None:
    """验证飞书创建工单对应的测试场景。"""
    key = "encrypt-key"
    client = TestClient(
        create_platform_app(
            build_memory_container(),
            feishu_encrypt_key=key,
            feishu_verification_token="verify-token",
        )
    )
    payload = {
        "event": {
            "message": {
                "message_id": "feishu-msg-1",
                "chat_id": "chat-1",
                "content": json.dumps({"text": "How do I use this product?"}),
            },
            "sender": {"sender_id": {"open_id": "open-1"}},
        }
    }
    body = json.dumps(payload).encode("utf-8")
    timestamp = "1700000000"
    nonce = "nonce-1"
    response = client.post(
        "/v1/events/feishu?tenant_id=tenant-1",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Lark-Request-Timestamp": timestamp,
            "X-Lark-Request-Nonce": nonce,
            "X-Lark-Signature": make_signature(timestamp, nonce, key, body),
        },
    )
    assert response.status_code == 200
    assert response.json()["source"] == "feishu"
    assert response.json()["status"] == "waiting_review"


def test_feishu_invalid_signature_is_rejected() -> None:
    """验证飞书无效签名是否拒绝对应的测试场景。"""
    client = TestClient(
        create_platform_app(build_memory_container(), feishu_encrypt_key="encrypt-key")
    )
    response = client.post(
        "/v1/events/feishu?tenant_id=tenant-1",
        json={"event": {}},
        headers={
            "X-Lark-Request-Timestamp": "1",
            "X-Lark-Request-Nonce": "2",
            "X-Lark-Signature": "invalid",
        },
    )
    assert response.status_code == 401
