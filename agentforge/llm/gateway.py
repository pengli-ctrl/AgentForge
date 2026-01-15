"""
LLM Gateway — LLM 推理服务的抽象封装。

封装 vLLM 推理接口，提供统一的 LLM 调用接口。
Agent 和工具通过 LLMGateway 调用 LLM，不直接依赖具体推理框架。

核心设计：
- 统一接口：无论后端是 vLLM、OpenAI API 还是本地模型，接口一致
- 异步调用：所有 LLM 请求都是异步的
- 工具调用支持：支持 function calling / tool calling
- 超时控制：每次调用都有硬性超时
- 重试机制：对 5xx 和连接错误自动重试，指数退避
"""

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
        name: 工具名称。
        arguments: 工具参数。
    """

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """LLM 响应的标准化格式。

    Attributes:
        content: LLM 生成的文本内容。
        tool_calls: LLM 请求执行的工具调用列表。
        has_tool_calls: 是否包含工具调用。
        usage: token 使用量统计。
        model: 使用的模型名称。
        latency: 响应延迟（秒）。
    """

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    has_tool_calls: bool = False
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    latency: float = 0.0


class LLMGateway(ABC):
    """LLM 网关抽象基类 — 统一 LLM 调用接口。

    无论后端是 vLLM 私有化部署、OpenAI API 还是本地模型，
    Agent 和工具都通过此接口调用 LLM。

    实现类需要实现 chat 方法，处理具体的 LLM 调用逻辑。

    Args:
        model: 模型名称。
        max_tokens: 单次生成的最大 token 数。
        timeout: 请求超时时间（秒）。
        temperature: 采样温度。
    """

    def __init__(
        self,
        model: str = "",
        max_tokens: int = 4096,
        timeout: float = 30.0,
        temperature: float = 0.7,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            model: str，调用方传入的 model 参数。
            max_tokens: int，调用方传入的 max_tokens 参数。
            timeout: float，调用方传入的 timeout 参数。
            temperature: float，调用方传入的 temperature 参数。

        Returns:
            None，函数执行后的结果。
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
            messages: 消息列表或纯文本 Prompt。
            tools: 可用工具的 JSON Schema 列表（function calling）。
            max_tokens: 单次生成的最大 token 数（覆盖默认值）。
            temperature: 采样温度（覆盖默认值）。

        Returns:
            标准化的 LLM 响应。
        """
        ...

    async def health_check(self) -> bool:
        """检查 LLM 服务是否可用。

        Returns:
            服务是否可用。
        """
        try:
            response = await self.chat("ping", max_tokens=10)
            return bool(response.content)
        except Exception as e:
            logger.error("LLM health check failed: %s", e)
            return False


class VLLMGateway(LLMGateway):
    """vLLM 推理服务的 Gateway 实现。

    封装 vLLM 的 OpenAI 兼容 API 接口，用于私有化部署场景。
    使用 httpx.AsyncClient 发送异步 HTTP 请求，支持超时控制和自动重试。

    重试策略：
    - 最多重试 3 次（共 4 次尝试）
    - 指数退避：1s → 2s → 4s
    - 仅对 5xx 服务端错误和连接错误重试
    - 4xx 客户端错误不重试（请求格式或认证问题）

    Args:
        endpoint: vLLM 服务的 API 端点。
        model: 模型名称。
        api_key: API 密钥（如果需要）。
        max_tokens: 单次生成的最大 token 数。
        timeout: 请求超时时间（秒）。
        temperature: 采样温度。
        _transport: httpx transport（用于测试注入 MockTransport）。
    """

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
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            endpoint: str，调用方传入的 endpoint 参数。
            model: str，调用方传入的 model 参数。
            api_key: str，调用方传入的 api_key 参数。
            max_tokens: int，调用方传入的 max_tokens 参数。
            timeout: float，调用方传入的 timeout 参数。
            temperature: float，调用方传入的 temperature 参数。
            _transport: Any，调用方传入的 _transport 参数。

        Returns:
            None，函数执行后的结果。
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
        """通过 vLLM 的 OpenAI 兼容 API 调用 LLM。

        使用 httpx.AsyncClient 发送 POST 请求到 {endpoint}/chat/completions，
        遵循 OpenAI API 请求/响应格式。支持自动重试和超时控制。

        如果 httpx 未安装，降级为返回空响应（不阻断调用方流程）。

        Args:
            messages: 消息列表或纯文本 Prompt。
            tools: 可用工具的 JSON Schema 列表。
            max_tokens: 单次生成的最大 token 数。
            temperature: 采样温度。

        Returns:
            标准化的 LLM 响应。

        Raises:
            LLMAPIError: 4xx 客户端错误（不重试）。
            LLMServiceUnavailable: 5xx 服务端错误，重试后仍失败。
            LLMConnectionError: 连接错误，重试后仍失败。
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
        """解析 vLLM OpenAI 兼容 API 的响应。

        从响应 JSON 中提取 content、tool_calls 和 usage。

        Args:
            data: vLLM API 返回的 JSON 数据。

        Returns:
            标准化的 LLMResponse 对象。
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
