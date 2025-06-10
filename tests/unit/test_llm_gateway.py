"""LLM Gateway 单元测试 — LLM 推理服务的抽象封装。

测试要点：请求路由、模型适配、响应解析、用量统计、错误重试。
"""

from __future__ import annotations

import json

import pytest

from agentforge.llm.gateway import (
    LLMAPIError,
    LLMConnectionError,
    LLMGateway,
    LLMResponse,
    LLMServiceUnavailable,
    ToolCall,
    VLLMGateway,
)
from tests.conftest import MockLLMGateway

# ──────────────────────────────────────────────────────────────────────────
# 辅助函数 — 构建 httpx MockTransport
# ──────────────────────────────────────────────────────────────────────────


def _make_mock_transport(
    response_body: dict,
    status_code: int = 200,
):
    """创建 httpx.MockTransport，返回指定的响应。

    Args:
        response_body: 响应 JSON 体。
        status_code: HTTP 状态码。

    Returns:
        httpx.MockTransport 实例。
    """
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=response_body)

    return httpx.MockTransport(handler)


def _make_mock_transport_sequence(
    responses: list[tuple[int, dict]],
):
    """创建 httpx.MockTransport，按顺序返回一系列响应。

    Args:
        responses: [(status_code, response_body), ...] 列表。

    Returns:
        httpx.MockTransport 实例。
    """
    import httpx

    iterator = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        try:
            status_code, body = next(iterator)
        except StopIteration:
            status_code, body = 500, {"error": "no more responses"}
        return httpx.Response(status_code, json=body)

    return httpx.MockTransport(handler)


def _make_mock_transport_error(error_cls):
    """创建 httpx.MockTransport，始终抛出指定的 httpx 异常。

    Args:
        error_cls: httpx 异常类（如 httpx.ConnectError）。

    Returns:
        httpx.MockTransport 实例。
    """
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        raise error_cls("simulated error")

    return httpx.MockTransport(handler)


# ──────────────────────────────────────────────────────────────────────────
# 数据类测试
# ──────────────────────────────────────────────────────────────────────────


class TestToolCall:
    """ToolCall 数据类测试。"""

    def test_default_arguments(self) -> None:
        call = ToolCall(name="search")
        assert call.name == "search"
        assert call.arguments == {}

    def test_with_arguments(self) -> None:
        call = ToolCall(name="search", arguments={"query": "test"})
        assert call.name == "search"
        assert call.arguments["query"] == "test"


class TestLLMResponse:
    """LLMResponse 数据类测试。"""

    def test_defaults(self) -> None:
        resp = LLMResponse()
        assert resp.content == ""
        assert resp.tool_calls == []
        assert resp.has_tool_calls is False
        assert resp.usage == {}
        assert resp.model == ""
        assert resp.latency == 0.0

    def test_with_tool_calls(self) -> None:
        resp = LLMResponse(
            content="",
            has_tool_calls=True,
            tool_calls=[ToolCall(name="echo", arguments={})],
            model="test-model",
        )
        assert resp.has_tool_calls is True
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "echo"


# ──────────────────────────────────────────────────────────────────────────
# 抽象基类测试
# ──────────────────────────────────────────────────────────────────────────


class TestLLMGatewayAbstract:
    """LLMGateway 抽象基类测试。"""

    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            LLMGateway()  # type: ignore[abstract]

    def test_init_params(self) -> None:
        gw = VLLMGateway(
            model="test-model",
            max_tokens=2048,
            timeout=10.0,
            temperature=0.5,
        )
        assert gw.model == "test-model"
        assert gw.max_tokens == 2048
        assert gw.timeout == 10.0
        assert gw.temperature == 0.5


# ──────────────────────────────────────────────────────────────────────────
# VLLMGateway 基础测试
# ──────────────────────────────────────────────────────────────────────────


class TestVLLMGateway:
    """VLLMGateway 测试。"""

    def test_init_defaults(self) -> None:
        gw = VLLMGateway()
        assert gw.endpoint == "http://localhost:8000/v1"
        assert gw.api_key == "EMPTY"
        assert gw.model == ""

    def test_init_custom(self) -> None:
        gw = VLLMGateway(
            endpoint="http://my-server:8080/v1",
            model="llama-3",
            api_key="secret-key",
        )
        assert gw.endpoint == "http://my-server:8080/v1"
        assert gw.api_key == "secret-key"
        assert gw.model == "llama-3"

    @pytest.mark.asyncio
    async def test_chat_returns_response(self) -> None:
        """测试 chat 方法返回标准 LLMResponse（使用 MockTransport）。"""
        transport = _make_mock_transport(
            {
                "choices": [{"message": {"content": "Hello!"}}],
                "model": "test",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        )
        gw = VLLMGateway(model="test", _transport=transport)
        resp = await gw.chat("hello")
        assert isinstance(resp, LLMResponse)
        assert resp.content == "Hello!"
        assert resp.model == "test"

    @pytest.mark.asyncio
    async def test_chat_with_string_prompt(self) -> None:
        """测试纯文本 prompt 自动转换为 messages 格式。"""
        transport = _make_mock_transport(
            {
                "choices": [{"message": {"content": "4"}}],
                "model": "test",
                "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
            }
        )
        gw = VLLMGateway(model="test", _transport=transport)
        resp = await gw.chat("What is 2+2?")
        assert isinstance(resp, LLMResponse)
        assert resp.content == "4"

    @pytest.mark.asyncio
    async def test_chat_with_message_list(self) -> None:
        """测试直接传入 messages 列表。"""
        transport = _make_mock_transport(
            {
                "choices": [{"message": {"content": "Hi there"}}],
                "model": "test",
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            }
        )
        gw = VLLMGateway(model="test", _transport=transport)
        resp = await gw.chat(
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Say hi"},
            ]
        )
        assert resp.content == "Hi there"


# ──────────────────────────────────────────────────────────────────────────
# VLLMGateway 响应解析测试
# ──────────────────────────────────────────────────────────────────────────


class TestVLLMGatewayResponseParsing:
    """VLLMGateway 响应解析测试。"""

    @pytest.mark.asyncio
    async def test_parse_tool_calls(self) -> None:
        """测试解析 tool_calls。"""
        transport = _make_mock_transport(
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "search",
                                        "arguments": json.dumps({"query": "test"}),
                                    }
                                },
                                {
                                    "function": {
                                        "name": "fetch",
                                        "arguments": json.dumps({"url": "http://x"}),
                                    }
                                },
                            ],
                        }
                    }
                ],
                "model": "llama-3",
                "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            }
        )
        gw = VLLMGateway(model="llama-3", _transport=transport)
        resp = await gw.chat("search and fetch")
        assert resp.has_tool_calls is True
        assert len(resp.tool_calls) == 2
        assert resp.tool_calls[0].name == "search"
        assert resp.tool_calls[0].arguments["query"] == "test"
        assert resp.tool_calls[1].name == "fetch"
        assert resp.tool_calls[1].arguments["url"] == "http://x"

    @pytest.mark.asyncio
    async def test_parse_usage(self) -> None:
        """测试解析 token 使用量。"""
        transport = _make_mock_transport(
            {
                "choices": [{"message": {"content": "ok"}}],
                "model": "test",
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            }
        )
        gw = VLLMGateway(model="test", _transport=transport)
        resp = await gw.chat("test")
        assert resp.usage["prompt_tokens"] == 100
        assert resp.usage["completion_tokens"] == 50
        assert resp.usage["total_tokens"] == 150

    @pytest.mark.asyncio
    async def test_parse_empty_content(self) -> None:
        """测试空 content 响应。"""
        transport = _make_mock_transport(
            {
                "choices": [{"message": {"content": ""}}],
                "model": "test",
                "usage": {},
            }
        )
        gw = VLLMGateway(model="test", _transport=transport)
        resp = await gw.chat("test")
        assert resp.content == ""
        assert resp.has_tool_calls is False

    @pytest.mark.asyncio
    async def test_parse_null_content(self) -> None:
        """测试 content 为 null 的响应（vLLM 工具调用时常见）。"""
        transport = _make_mock_transport(
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [{"function": {"name": "run", "arguments": "{}"}}],
                        }
                    }
                ],
                "model": "test",
                "usage": {"total_tokens": 10},
            }
        )
        gw = VLLMGateway(model="test", _transport=transport)
        resp = await gw.chat("test")
        assert resp.content == ""
        assert resp.has_tool_calls is True

    @pytest.mark.asyncio
    async def test_latency_recorded(self) -> None:
        """测试响应延迟被记录。"""
        transport = _make_mock_transport(
            {
                "choices": [{"message": {"content": "ok"}}],
                "model": "test",
                "usage": {},
            }
        )
        gw = VLLMGateway(model="test", _transport=transport)
        resp = await gw.chat("test")
        assert resp.latency >= 0.0

    @pytest.mark.asyncio
    async def test_invalid_tool_call_arguments(self) -> None:
        """测试 tool_call arguments 不是有效 JSON 时优雅降级。"""
        transport = _make_mock_transport(
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {"function": {"name": "bad", "arguments": "not-json{["}}
                            ],
                        }
                    }
                ],
                "model": "test",
                "usage": {},
            }
        )
        gw = VLLMGateway(model="test", _transport=transport)
        resp = await gw.chat("test")
        assert resp.has_tool_calls is True
        assert resp.tool_calls[0].name == "bad"
        assert resp.tool_calls[0].arguments == {}


# ──────────────────────────────────────────────────────────────────────────
# VLLMGateway 错误处理与重试测试
# ──────────────────────────────────────────────────────────────────────────


class TestVLLMGatewayRetry:
    """VLLMGateway 重试和错误处理测试。"""

    @pytest.mark.asyncio
    async def test_no_retry_on_4xx(self) -> None:
        """4xx 客户端错误不重试，直接抛出 LLMAPIError。"""
        transport = _make_mock_transport(
            {"error": "bad request"},
            status_code=400,
        )
        gw = VLLMGateway(model="test", _transport=transport, timeout=5.0)
        with pytest.raises(LLMAPIError, match="400"):
            await gw.chat("test")

    @pytest.mark.asyncio
    async def test_retry_on_5xx_then_success(self) -> None:
        """5xx 错误重试，最终成功。"""
        transport = _make_mock_transport_sequence(
            [
                (503, {"error": "unavailable"}),
                (503, {"error": "unavailable"}),
                (
                    200,
                    {
                        "choices": [{"message": {"content": "recovered"}}],
                        "model": "test",
                        "usage": {"total_tokens": 5},
                    },
                ),
            ]
        )
        gw = VLLMGateway(model="test", _transport=transport, timeout=5.0)
        resp = await gw.chat("test")
        assert resp.content == "recovered"

    @pytest.mark.asyncio
    async def test_retry_exhausted_on_5xx(self) -> None:
        """5xx 错误重试耗尽后抛出 LLMServiceUnavailable。"""
        transport = _make_mock_transport(
            {"error": "unavailable"},
            status_code=500,
        )
        gw = VLLMGateway(model="test", _transport=transport, timeout=5.0)
        with pytest.raises(LLMServiceUnavailable, match="500"):
            await gw.chat("test")

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self) -> None:
        """连接错误重试耗尽后抛出 LLMConnectionError。"""
        import httpx

        transport = _make_mock_transport_error(httpx.ConnectError)
        gw = VLLMGateway(model="test", _transport=transport, timeout=5.0)
        with pytest.raises(LLMConnectionError, match="Failed to connect"):
            await gw.chat("test")

    @pytest.mark.asyncio
    async def test_retry_on_connect_timeout(self) -> None:
        """连接超时重试耗尽后抛出 LLMConnectionError。"""
        import httpx

        transport = _make_mock_transport_error(httpx.ConnectTimeout)
        gw = VLLMGateway(model="test", _transport=transport, timeout=5.0)
        with pytest.raises(LLMConnectionError):
            await gw.chat("test")

    @pytest.mark.asyncio
    async def test_retry_on_read_timeout(self) -> None:
        """读取超时重试耗尽后抛出 LLMConnectionError。"""
        import httpx

        transport = _make_mock_transport_error(httpx.ReadTimeout)
        gw = VLLMGateway(model="test", _transport=transport, timeout=5.0)
        with pytest.raises(LLMConnectionError):
            await gw.chat("test")

    @pytest.mark.asyncio
    async def test_connection_error_then_success(self) -> None:
        """连接错误后重试成功。"""
        import httpx

        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.ConnectError("simulated")
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "model": "test",
                    "usage": {"total_tokens": 5},
                },
            )

        transport = httpx.MockTransport(handler)
        gw = VLLMGateway(model="test", _transport=transport, timeout=5.0)
        resp = await gw.chat("test")
        assert resp.content == "ok"

    @pytest.mark.asyncio
    async def test_health_check_success_with_transport(self) -> None:
        """使用 MockTransport 测试 health_check 成功。"""
        transport = _make_mock_transport(
            {
                "choices": [{"message": {"content": "pong"}}],
                "model": "test",
                "usage": {},
            }
        )
        gw = VLLMGateway(model="test", _transport=transport)
        result = await gw.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure_with_5xx(self) -> None:
        """5xx 错误导致 health_check 返回 False。"""
        transport = _make_mock_transport(
            {"error": "unavailable"},
            status_code=503,
        )
        gw = VLLMGateway(model="test", _transport=transport, timeout=5.0)
        result = await gw.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_request_body_format(self) -> None:
        """验证请求体遵循 OpenAI API 规范。"""
        import httpx

        captured_request = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_request["body"] = json.loads(request.content)
            captured_request["headers"] = dict(request.headers)
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "model": "test",
                    "usage": {},
                },
            )

        transport = httpx.MockTransport(handler)
        gw = VLLMGateway(
            model="llama-3",
            api_key="sk-test",
            max_tokens=100,
            temperature=0.5,
            _transport=transport,
        )
        await gw.chat("hello", tools=[{"type": "function", "function": {"name": "f"}}])

        body = captured_request["body"]
        assert body["model"] == "llama-3"
        assert body["messages"] == [{"role": "user", "content": "hello"}]
        assert body["max_tokens"] == 100
        assert body["temperature"] == 0.5
        assert body["tools"] == [{"type": "function", "function": {"name": "f"}}]
        assert captured_request["headers"]["authorization"] == "Bearer sk-test"

    @pytest.mark.asyncio
    async def test_url_construction(self) -> None:
        """验证 URL 拼接正确：{endpoint}/chat/completions。"""
        import httpx

        captured_url = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_url["url"] = str(request.url)
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "model": "test",
                    "usage": {},
                },
            )

        transport = httpx.MockTransport(handler)
        gw = VLLMGateway(
            endpoint="http://my-server:8080/v1",
            model="test",
            _transport=transport,
        )
        await gw.chat("test")
        assert captured_url["url"] == "http://my-server:8080/v1/chat/completions"


# ──────────────────────────────────────────────────────────────────────────
# MockLLMGateway 测试
# ──────────────────────────────────────────────────────────────────────────


class TestMockLLMGateway:
    """MockLLMGateway 测试（复用 conftest fixture）。"""

    @pytest.mark.asyncio
    async def test_default_response(self, mock_llm: MockLLMGateway) -> None:
        resp = await mock_llm.chat("hello")
        assert resp.content == "Mock LLM response."
        assert resp.model == "mock-model"
        assert mock_llm.call_count == 1

    @pytest.mark.asyncio
    async def test_scripted_responses(self) -> None:
        gw = MockLLMGateway(
            responses=[
                LLMResponse(content="first", model="m"),
                LLMResponse(content="second", model="m"),
            ]
        )
        r1 = await gw.chat("q1")
        r2 = await gw.chat("q2")
        r3 = await gw.chat("q3")  # 超出脚本，返回默认
        assert r1.content == "first"
        assert r2.content == "second"
        assert r3.content == "Mock LLM response."

    @pytest.mark.asyncio
    async def test_call_count_increments(self) -> None:
        gw = MockLLMGateway()
        assert gw.call_count == 0
        await gw.chat("a")
        await gw.chat("b")
        assert gw.call_count == 2


# ──────────────────────────────────────────────────────────────────────────
# 健康检查测试
# ──────────────────────────────────────────────────────────────────────────


class TestHealthCheck:
    """健康检查测试。"""

    @pytest.mark.asyncio
    async def test_health_check_success(self) -> None:
        gw = MockLLMGateway(responses=[LLMResponse(content="pong", model="mock")])
        result = await gw.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        class FailingGateway(LLMGateway):
            async def chat(self, messages, tools=None, max_tokens=None, temperature=None):
                raise ConnectionError("LLM service unavailable")

        gw = FailingGateway(model="test")
        result = await gw.health_check()
        assert result is False
