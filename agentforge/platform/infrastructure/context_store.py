"""Persistent context-store backends."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from agentforge.core.context_store import ContextStore


class RedisContextStore:
    """Redis-backed context store with explicit tenant/session/dag namespace."""

    def __init__(self, client: Any, *, prefix: str = "agentforge:context", ttl_seconds: int = 3600) -> None:
        self._client = client
        self._prefix = prefix.rstrip(":")
        self._ttl = ttl_seconds

    def _key(self, namespace: str) -> str:
        return f"{self._prefix}:{namespace}"

    async def initialize(self, input_data: dict) -> None:
        key = self._key("input")
        await self._client.delete(key)
        if input_data:
            await self._client.hset(key, mapping={k: json.dumps(v, default=str) for k, v in input_data.items()})
            if self._ttl > 0:
                await self._client.expire(key, self._ttl)

    async def write(self, key: str, value: Any) -> None:
        store_key = self._key("store")
        await self._client.hset(store_key, key, json.dumps(value, default=str))
        if self._ttl > 0:
            await self._client.expire(store_key, self._ttl)

    async def read(self, key: str) -> Any | None:
        raw = await self._client.hget(self._key("store"), key)
        return json.loads(raw) if raw is not None else None

    async def read_with_mapping(self, input_mapping: Mapping[str, str]) -> dict[str, Any]:
        store = await self.get_all()
        input_data = await self.get_input()
        resolved: dict[str, Any] = {}
        for target, ref in input_mapping.items():
            if ref.startswith("$ctx."):
                resolved[target] = store.get(ref[5:])
            elif ref.startswith("$input."):
                resolved[target] = input_data.get(ref[7:])
            else:
                resolved[target] = ref
        return resolved

    async def get_all(self) -> dict[str, Any]:
        raw = await self._client.hgetall(self._key("store"))
        return {key: json.loads(value) for key, value in raw.items()}

    async def get_input(self) -> dict[str, Any]:
        raw = await self._client.hgetall(self._key("input"))
        return {key: json.loads(value) for key, value in raw.items()}

    async def has(self, key: str) -> bool:
        return bool(await self._client.hexists(self._key("store"), key))

    async def delete(self, key: str) -> bool:
        return bool(await self._client.hdel(self._key("store"), key))

    async def clear(self) -> None:
        await self._client.delete(self._key("store"), self._key("input"), self._key("access"))

    def size(self) -> int:
        raise RuntimeError("size() is not synchronous for Redis; use await size_async()")

    async def size_async(self) -> int:
        return int(await self._client.hlen(self._key("store")))

    async def log_access(self, node_id: str, keys_read: list[str]) -> None:
        payload = json.dumps({"node_id": node_id, "keys_read": keys_read}, default=str)
        await self._client.rpush(self._key("access"), payload)
        if self._ttl > 0:
            await self._client.expire(self._key("access"), self._ttl)

    async def get_access_log(self) -> list[dict]:
        raw = await self._client.lrange(self._key("access"), 0, -1)
        return [json.loads(item) for item in raw]


def build_context_store(settings: Any, client: Any | None = None):
    if settings.context_store_backend == "memory":
        return ContextStore()
    if settings.context_store_backend == "redis":
        if client is None:
            import redis.asyncio as aioredis
            client = aioredis.from_url(settings.valkey_url, decode_responses=True)
        return RedisContextStore(client, ttl_seconds=settings.context_store_ttl_seconds)
    raise ValueError(f"unsupported context_store_backend: {settings.context_store_backend}")
