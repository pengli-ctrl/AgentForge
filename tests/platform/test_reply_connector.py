import json

import pytest

from agentforge.platform.infrastructure.feishu_reply_connector import FeishuReplyConnector


@pytest.mark.asyncio
async def test_feishu_reply_connector_sends_text_and_caches_token() -> None:
    calls: list[tuple[str, str, dict]] = []

    async def fake_request(method: str, url: str, **kwargs) -> dict:
        calls.append((method, url, kwargs))
        if url == FeishuReplyConnector.TOKEN_URL:
            return {"tenant_access_token": "token-1"}
        return {"code": 0, "data": {"message_id": "om_1"}}

    connector = FeishuReplyConnector("app-id", "app-secret", request_fn=fake_request)

    first = await connector.send_text("chat-1", "hello", "reply-1")
    second = await connector.send_text("chat-2", "world", "reply-2")

    assert first["message_id"] == "om_1"
    assert second["message_id"] == "om_1"
    assert [call[1] for call in calls].count(FeishuReplyConnector.TOKEN_URL) == 1

    method, url, kwargs = calls[1]
    assert method == "POST"
    assert url == FeishuReplyConnector.MESSAGE_URL
    assert kwargs["params"] == {"receive_id_type": "chat_id", "uuid": "reply-1"}
    assert kwargs["headers"] == {"Authorization": "Bearer token-1"}
    assert kwargs["json"]["receive_id"] == "chat-1"
    assert kwargs["json"]["msg_type"] == "text"
    assert json.loads(kwargs["json"]["content"]) == {"text": "hello"}


@pytest.mark.asyncio
async def test_feishu_reply_connector_propagates_request_failure() -> None:
    async def failing_request(method: str, url: str, **kwargs) -> dict:
        raise RuntimeError("feishu unavailable")

    connector = FeishuReplyConnector("app-id", "app-secret", request_fn=failing_request)

    with pytest.raises(RuntimeError, match="feishu unavailable"):
        await connector.send_text("chat-1", "hello", "reply-1")


@pytest.mark.asyncio
async def test_feishu_reply_connector_rejects_api_error() -> None:
    async def fake_request(method: str, url: str, **kwargs) -> dict:
        if url == FeishuReplyConnector.TOKEN_URL:
            return {"code": 0, "tenant_access_token": "token-1", "expire": 7200}
        return {"code": 230001, "msg": "invalid receive_id"}

    connector = FeishuReplyConnector("app-id", "app-secret", request_fn=fake_request)

    with pytest.raises(RuntimeError, match="invalid receive_id"):
        await connector.send_text("chat-1", "hello", "reply-1")
