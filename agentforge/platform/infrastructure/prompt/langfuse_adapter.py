"""解析 Langfuse 提示词版本。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx


class LangfusePromptAdapter:
    """解析 Langfuse 提示词版本。"""

    def __init__(
        self,
        base_url: str,
        public_key: str = "",
        secret_key: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """解析 Langfuse 提示词版本。

        Args:
            base_url: 调用该函数所需的输入值。
            public_key: 调用该函数所需的输入值。
            secret_key: 调用该函数所需的输入值。
            client: 调用该函数所需的输入值。
        """
        self._base_url = base_url.rstrip("/")
        self._auth = (public_key, secret_key) if public_key and secret_key else None
        self._client = client or httpx.AsyncClient(timeout=3.0)
        self._owns_client = client is None

    async def resolve(self, name: str, *, label: str = "production") -> Mapping[str, Any]:
        """解析 Langfuse 提示词版本。

            Args:
                name: 调用该函数所需的输入值。
                label: 调用该函数所需的输入值。

            Returns:
        当前操作的结构化结果。
        """
        response = await self._client.get(
            f"{self._base_url}/api/public/v2/prompts/{name}",
            params={"label": label},
            auth=self._auth,
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "name": name,
            "label": label,
            "version": payload.get("version"),
            "prompt": payload.get("prompt", payload),
        }

    async def close(self) -> None:
        """解析 Langfuse 提示词版本。"""
        if self._owns_client:
            await self._client.aclose()
