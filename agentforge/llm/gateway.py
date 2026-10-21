"""网关模块。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class LLMConnectionError(Exception):
    """LLM 连接错误 — 无法连接到 LLM 服务（网络超时、DNS 解析失败等）。"""


class LLMAPIError(Exception):
    """LLM API 错误 — 客户端错误（4xx），如认证失败、请求格式错误。"""


class LLMServiceUnavailable(Exception):
    """LLM 服务不可用 — 服务端错误（5xx），重试后仍失败。"""


@dataclass
class ToolCall:
    """LLM 请求执行的工具调用。

    Attributes:
        name: 名称。
        arguments: 参数。
    """

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """LLM 响应的标准化格式。

    Attributes:
        content: 写入内容。
        tool_calls: 工具调用。
        has_tool_calls: 具有工具调用。
        usage: 用量。
        model: 模型。
        latency: 延迟。
    """

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    has_tool_calls: bool = False
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    latency: float = 0.0


class LLMGateway(ABC):
    """LLM 网关抽象基类 — 统一 LLM 调用接口。"""

    def __init__(
        self,
        model: str = "",
        max_tokens: int = 4096,
        timeout: float = 30.0,
        temperature: float = 0.7,
    ) -> None:
        """初始化 LLMGateway。

        Args:
            model: 模型标识或模型对象。
            max_tokens: 生成结果允许使用的最大 Token 数。
            timeout: 操作超时时间。
            temperature: 模型采样温度。
        """
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.temperature = temperature

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]] | str,
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """调用 LLM 进行对话。

        Args:
            messages: 消息列表。
            tools: 可供模型调用的工具定义。
            max_tokens: 生成结果允许使用的最大 Token 数。
            temperature: 模型采样温度。

        Returns:
            LLM 响应对象。
        """
        ...

    async def health_check(self) -> bool:
        """检查 LLM 服务是否可用。

        Returns:
            操作是否成功。
        """
        try:
            response = await self.chat("ping", max_tokens=10)
            return bool(response.content)
        except Exception as e:
            logger.error("LLM health check failed: %s", e)
            return False


class VLLMGateway(LLMGateway):
    """VLLM 网关抽象。"""

    def __init__(
        self,
        endpoint: str = "http://localhost:8000/v1",
        model: str = "",
        api_key: str = "EMPTY",
        max_tokens: int = 4096,
        timeout: float = 30.0,
        temperature: float = 0.7,
        _transport: Any = None,
    ) -> None:
        """初始化 VLLMGateway。

        Args:
            endpoint: 端点。
            model: 模型标识或模型对象。
            api_key: API键。
            max_tokens: 生成结果允许使用的最大 Token 数。
            timeout: 操作超时时间。
            temperature: 模型采样温度。
            _transport: 传输层。
        """
        super().__init__(model, max_tokens, timeout, temperature)
        self.endpoint = endpoint
        self.api_key = api_key
        self._transport = _transport

    async def chat(
        self,
        messages: list[dict[str, str]] | str,
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """发送VLLM 网关。

        Args:
            messages: 消息列表。
            tools: 可供模型调用的工具定义。
            max_tokens: 生成结果允许使用的最大 Token 数。
            temperature: 模型采样温度。

        Returns:
            LLM 响应对象。

        Raises:
            LLMAPIError: 操作无法完成时抛出。
            LLMServiceUnavailable: 操作无法完成时抛出。
            LLMConnectionError: 操作无法完成时抛出。
        """
        # 规范化消息格式
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        # 尝试导入 httpx，不可用则降级
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not installed, VLLMGateway falling back to empty response")
            return LLMResponse(content="", model=self.model, usage={})

        # 构建请求体（遵循 OpenAI API 规范）
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if tools:
            body["tools"] = tools

        # 构建请求头
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.endpoint}/chat/completions"

        # 重试参数
        max_retries = 3
        backoff_times = [1, 2, 4]

        for attempt in range(max_retries + 1):
            try:
                start_time = time.monotonic()

                client_kwargs: dict[str, Any] = {"timeout": self.timeout}
                if self._transport is not None:
                    client_kwargs["transport"] = self._transport

                async with httpx.AsyncClient(**client_kwargs) as client:
                    http_resp = await client.post(url, json=body, headers=headers)

                elapsed = time.monotonic() - start_time

                # 4xx 客户端错误 — 不重试
                if 400 <= http_resp.status_code < 500:
                    logger.error(
                        "LLM API client error (status=%d, body=%s)",
                        http_resp.status_code,
                        http_resp.text[:500],
                    )
                    raise LLMAPIError(
                        f"LLM API error (status={http_resp.status_code}): " f"{http_resp.text}"
                    )

                # 5xx 服务端错误 — 重试
                if http_resp.status_code >= 500:
                    if attempt < max_retries:
                        wait = backoff_times[attempt]
                        logger.warning(
                            "LLM 5xx error (status=%d, attempt=%d/%d), " "retrying in %ds",
                            http_resp.status_code,
                            attempt + 1,
                            max_retries + 1,
                            wait,
                        )
                        await asyncio.sleep(wait)
                        continue
                    raise LLMServiceUnavailable(
                        f"LLM service unavailable (status={http_resp.status_code}) "
                        f"after {max_retries + 1} attempts"
                    )

                # 成功 — 解析响应
                data = http_resp.json()
                response = self._parse_vllm_response(data)
                response.latency = elapsed
                return response

            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                if attempt < max_retries:
                    wait = backoff_times[attempt]
                    logger.warning(
                        "LLM connection error (attempt=%d/%d): %s, retrying in %ds",
                        attempt + 1,
                        max_retries + 1,
                        e,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                raise LLMConnectionError(
                    f"Failed to connect to LLM service after " f"{max_retries + 1} attempts: {e}"
                ) from e

        # 理论上不会到达这里
        return LLMResponse(content="", model=self.model, usage={})

    def _parse_vllm_response(self, data: dict[str, Any]) -> LLMResponse:
        """解析VLLM响应。

        Args:
            data: 待处理数据。

        Returns:
            处理结果对象。
        """
        choices = data.get("choices", [])
        choice = choices[0] if choices else {}
        message = choice.get("message", {})

        content = message.get("content", "") or ""

        # 解析 tool_calls
        tool_calls: list[ToolCall] = []
        raw_tool_calls = message.get("tool_calls", [])
        for tc in raw_tool_calls:
            function = tc.get("function", {})
            raw_args = function.get("arguments", "{}")
            try:
                arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except (json.JSONDecodeError, TypeError):
                arguments = {}
            tool_calls.append(
                ToolCall(
                    name=function.get("name", ""),
                    arguments=arguments,
                )
            )

        # 解析 usage
        usage_data = data.get("usage", {})
        usage = {
            "prompt_tokens": usage_data.get("prompt_tokens", 0),
            "completion_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
        }

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            has_tool_calls=bool(tool_calls),
            usage=usage,
            model=data.get("model", self.model),
        )
