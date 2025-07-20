import hashlib
import json

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.runtime import build_memory_container


def make_signature(timestamp: str, nonce: str, key: str, body: bytes) -> str:
    payload = timestamp + nonce + key + body.decode("utf-8")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_feishu_challenge() -> None:
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
