"""提供架构升级适配。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx


class LangfusePromptAdapter:
    """提供架构升级适配。
    """
    def __init__(self, base_url: str, public_key: str = "", secret_key: str = "", client: httpx.AsyncClient | None = None) -> None:
        """提供架构升级适配。

        Args:
            base_url: 输入参数。
            public_key: 输入参数。
            secret_key: 输入参数。
            client: 输入参数。
        """
        self._base_url = base_url.rstrip("/")
        self._auth = (public_key, secret_key) if public_key and secret_key else None
        self._client = client or httpx.AsyncClient(timeout=3.0)
        self._owns_client = client is None

    async def resolve(self, name: str, *, label: str = "production") -> Mapping[str, Any]:
        """提供架构升级适配。

        Args:
            name: 输入参数。
            label: 输入参数。

        Returns:
    处理结果。
        """
        response = await self._client.get(
            f"{self._base_url}/api/public/v2/prompts/{name}",
            params={"label": label},
            auth=self._auth,
        )
        response.raise_for_status()
        payload = response.json()
        return {"name": name, "label": label, "version": payload.get("version"), "prompt": payload.get("prompt", payload)}

    async def close(self) -> None:
        """提供架构升级适配。
        """
        if self._owns_client:
            await self._client.aclose()
