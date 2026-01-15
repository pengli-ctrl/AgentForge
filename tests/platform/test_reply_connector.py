"""AgentForge 平台测试层：test_reply_connector。

本测试模块验证 test_reply_connector 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_feishu_reply_connector_sends_text_and_caches_token、test_feishu_reply_connector_propagates_request_failure、test_feishu_reply_connector_rejects_api_error。
"""

import json

import pytest

from agentforge.platform.infrastructure.feishu_reply_connector import FeishuReplyConnector


@pytest.mark.asyncio
async def test_feishu_reply_connector_sends_text_and_caches_token() -> None:
    """验证 feishu_reply_connector_sends_text_and_caches_token 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    calls: list[tuple[str, str, dict]] = []

    async def fake_request(method: str, url: str, **kwargs) -> dict:
        """执行 fake_request 对应的逻辑，并返回处理结果。

        Args:
            method: str，调用方传入的 method 参数。
            url: str，调用方传入的 url 参数。
            **kwargs: Any，调用方传入的 **kwargs 参数。

        Returns:
            dict，函数执行后的结果。
        """
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
    """验证 feishu_reply_connector_propagates_request_failure 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。

    Raises:
        RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
    """

    async def failing_request(method: str, url: str, **kwargs) -> dict:
        """执行 failing_request 对应的逻辑，并返回处理结果。

        Args:
            method: str，调用方传入的 method 参数。
            url: str，调用方传入的 url 参数。
            **kwargs: Any，调用方传入的 **kwargs 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        raise RuntimeError("feishu unavailable")

    connector = FeishuReplyConnector("app-id", "app-secret", request_fn=failing_request)

    with pytest.raises(RuntimeError, match="feishu unavailable"):
        await connector.send_text("chat-1", "hello", "reply-1")


@pytest.mark.asyncio
async def test_feishu_reply_connector_rejects_api_error() -> None:
    """验证 feishu_reply_connector_rejects_api_error 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """

    async def fake_request(method: str, url: str, **kwargs) -> dict:
        """执行 fake_request 对应的逻辑，并返回处理结果。

        Args:
            method: str，调用方传入的 method 参数。
            url: str，调用方传入的 url 参数。
            **kwargs: Any，调用方传入的 **kwargs 参数。

        Returns:
            dict，函数执行后的结果。
        """
        if url == FeishuReplyConnector.TOKEN_URL:
            return {"code": 0, "tenant_access_token": "token-1", "expire": 7200}
        return {"code": 230001, "msg": "invalid receive_id"}

    connector = FeishuReplyConnector("app-id", "app-secret", request_fn=fake_request)

    with pytest.raises(RuntimeError, match="invalid receive_id"):
        await connector.send_text("chat-1", "hello", "reply-1")
