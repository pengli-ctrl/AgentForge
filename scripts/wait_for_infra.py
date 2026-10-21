"""用于基础设施模块。"""

from __future__ import annotations

import asyncio
import os
import time

import asyncpg
import httpx
import redis.asyncio as redis
from temporalio.client import Client


async def _check() -> None:
    """执行内部一致性检查。"""
    connection = await asyncpg.connect(
        host=os.environ.get("AGENTFORGE_POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("AGENTFORGE_POSTGRES_PORT", "5432")),
        user=os.environ.get("AGENTFORGE_POSTGRES_USER", "agentforge"),
        password=os.environ.get("AGENTFORGE_POSTGRES_PASSWORD", "agentforge"),
        database="postgres",
    )
    await connection.close()
    client = redis.from_url(os.environ.get("AGENTFORGE_VALKEY_URL", "redis://localhost:6379/0"))
    try:
        await client.ping()
    finally:
        await client.aclose()
    async with httpx.AsyncClient(timeout=3) as http:
        endpoint = os.environ.get("AGENTFORGE_OBJECT_STORE_ENDPOINT", "http://localhost:9000")
        response = await http.get(f"{endpoint.rstrip('/')}/minio/health/live")
        response.raise_for_status()
    temporal = await Client.connect(
        os.environ.get("AGENTFORGE_TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.environ.get("AGENTFORGE_TEMPORAL_NAMESPACE", "default"),
    )
    del temporal


async def main() -> None:
    """执行主流程。

    Raises:
        SystemExit: 操作无法完成时抛出。
    """
    deadline = time.monotonic() + 120
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            await _check()
            print("AgentForge infrastructure is ready")
            return
        except Exception as exc:  # noqa: BLE001 - readiness polling
            last_error = exc
            await asyncio.sleep(2)
    raise SystemExit(f"infrastructure did not become ready: {last_error}")


if __name__ == "__main__":
    asyncio.run(main())
