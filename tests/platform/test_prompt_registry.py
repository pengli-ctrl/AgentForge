"""提供架构升级适配。"""
import httpx
import pytest

from agentforge.platform.infrastructure.prompt.langfuse_adapter import LangfusePromptAdapter


@pytest.mark.asyncio
async def test_langfuse_prompt_resolution() -> None:
    """提供架构升级适配。
    """
    def handler(request: httpx.Request) -> httpx.Response:
        """提供架构升级适配。

        Args:
            request: 输入参数。

        Returns:
    处理结果。
        """
        assert request.url.params["label"] == "production"
        return httpx.Response(200, json={"version": 7, "prompt": [{"role": "system", "content": "hello"}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = LangfusePromptAdapter("http://langfuse:3000", client=client)
    result = await adapter.resolve("support-reply")
    assert result["version"] == 7
    assert result["prompt"][0]["role"] == "system"
    await client.aclose()
