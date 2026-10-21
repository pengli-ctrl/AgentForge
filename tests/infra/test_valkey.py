"""测试Valkey测试模块。"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from agentforge.platform.infrastructure.valkey_coordination import ValkeyCoordination
from tests.infra.conftest import RUN_INFRA

pytestmark = [
    pytest.mark.infra,
    pytest.mark.skipif(not RUN_INFRA, reason="set AGENTFORGE_RUN_INFRA_TESTS=1"),
]


@pytest.mark.asyncio
async def test_valkey_coordination_primitives_against_real_valkey() -> None:
    """验证Valkey协调针对真实Valkey对应的测试场景。"""
    url = os.environ.get("AGENTFORGE_VALKEY_URL", "redis://localhost:6379/0")
    coordination = ValkeyCoordination.from_url(url, prefix=f"infra-{uuid4()}")
    try:
        assert await coordination.ping() is True
        assert (await coordination.rate_limit("api", capacity=2, refill_rate=1)).allowed is True
        assert (await coordination.rate_limit("api", capacity=2, refill_rate=1)).allowed is True
        blocked = await coordination.rate_limit("api", capacity=2, refill_rate=1)
        assert blocked.allowed is False
        assert blocked.retry_after_ms > 0

        await coordination.set_json("tenant-a:doc:1", {"title": "A"}, ttl_seconds=30)
        await coordination.set_json("tenant-a:doc:2", {"title": "B"}, ttl_seconds=30)
        assert await coordination.get_json("tenant-a:doc:1") == {"title": "A"}
        assert await coordination.invalidate_prefix("tenant-a:") == 2
        assert await coordination.get_json("tenant-a:doc:1") is None

        assert await coordination.acquire_lock("job", "owner-a", ttl_seconds=30) is True
        assert await coordination.acquire_lock("job", "owner-b", ttl_seconds=30) is False
        assert await coordination.release_lock("job", "owner-b") is False
        assert await coordination.release_lock("job", "owner-a") is True
    finally:
        await coordination.close()
