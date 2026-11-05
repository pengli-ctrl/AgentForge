"""Architecture-upgrade ports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class AuthPort(Protocol):
    async def authenticate(self, token: str) -> Mapping[str, Any]: ...


class PolicyPort(Protocol):
    async def authorize(self, *, tenant_id: str, principal: str, action: str, resource_type: str, resource_id: str, context: Mapping[str, Any] | None = None) -> Mapping[str, Any]: ...


class RateLimitPort(Protocol):
    async def acquire(self, key: str, *, cost: int = 1) -> bool: ...
    async def release(self, key: str, *, cost: int = 1) -> None: ...


class ContextStorePort(Protocol):
    async def write(self, key: str, value: Any) -> None: ...
    async def read(self, key: str) -> Any | None: ...
    async def delete(self, key: str) -> bool: ...
    async def clear(self) -> None: ...


class PromptRegistryPort(Protocol):
    async def resolve(self, name: str, *, label: str = "production") -> Mapping[str, Any]: ...


class RagParserPort(Protocol):
    async def parse(self, content: bytes, *, content_type: str = "", filename: str = "") -> Mapping[str, Any]: ...


class DagExecutorPort(Protocol):
    async def execute(self, dag: Mapping[str, Any], *, context_id: str) -> Mapping[str, Any]: ...
