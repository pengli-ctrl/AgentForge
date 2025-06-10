"""RedisStateStore 单元测试 — 快照持久化与状态恢复。

测试要点：快照持久化、状态恢复（使用内存回退，不依赖真实 Redis）。
"""

from __future__ import annotations

import pytest

from agentforge.storage.redis_state import RedisStateStore


@pytest.fixture
def store() -> RedisStateStore:
    """创建内存回退的 RedisStateStore（不连接真实 Redis）。"""
    return RedisStateStore(
        redis_url="redis://localhost:6379",
        key_prefix="agentforge:snapshot",
        default_ttl=3600,
    )


class TestInit:
    """初始化测试。"""

    def test_default_values(self) -> None:
        s = RedisStateStore()
        assert s.redis_url == "redis://localhost:6379"
        assert s.key_prefix == "agentforge:snapshot"
        assert s.default_ttl == 86400

    def test_custom_values(self) -> None:
        s = RedisStateStore(
            redis_url="redis://my-host:6380",
            key_prefix="custom:prefix",
            default_ttl=7200,
        )
        assert s.redis_url == "redis://my-host:6380"
        assert s.key_prefix == "custom:prefix"
        assert s.default_ttl == 7200

    def test_no_redis_on_init(self, store: RedisStateStore) -> None:
        assert store._redis is None
        assert store._fallback == {}


class TestSaveAndLoad:
    """保存和加载快照测试。"""

    @pytest.mark.asyncio
    async def test_save_and_load_snapshot(self, store: RedisStateStore) -> None:
        snapshot = {"agent": "review", "result": "ok", "version": 1}
        await store.save_snapshot("corr-001", 1, snapshot)
        loaded = await store.load_snapshot("corr-001", 1)
        assert loaded == snapshot

    @pytest.mark.asyncio
    async def test_load_nonexistent_returns_none(self, store: RedisStateStore) -> None:
        result = await store.load_snapshot("corr-missing", 1)
        assert result is None

    @pytest.mark.asyncio
    async def test_save_multiple_versions(self, store: RedisStateStore) -> None:
        for v in range(1, 4):
            await store.save_snapshot("corr-002", v, {"version": v})

        v1 = await store.load_snapshot("corr-002", 1)
        v2 = await store.load_snapshot("corr-002", 2)
        v3 = await store.load_snapshot("corr-002", 3)
        assert v1["version"] == 1
        assert v2["version"] == 2
        assert v3["version"] == 3


class TestLoadLatest:
    """加载最新快照测试。"""

    @pytest.mark.asyncio
    async def test_load_latest_snapshot(self, store: RedisStateStore) -> None:
        await store.save_snapshot("corr-003", 1, {"v": 1})
        await store.save_snapshot("corr-003", 2, {"v": 2})
        await store.save_snapshot("corr-003", 5, {"v": 5})

        latest = await store.load_latest_snapshot("corr-003")
        assert latest is not None
        assert latest["v"] == 5

    @pytest.mark.asyncio
    async def test_load_latest_no_snapshots(self, store: RedisStateStore) -> None:
        result = await store.load_latest_snapshot("corr-empty")
        assert result is None


class TestDelete:
    """删除快照测试。"""

    @pytest.mark.asyncio
    async def test_delete_snapshots(self, store: RedisStateStore) -> None:
        await store.save_snapshot("corr-004", 1, {"a": 1})
        await store.save_snapshot("corr-004", 2, {"a": 2})
        count = await store.delete_snapshots("corr-004")
        assert count == 2
        assert await store.load_snapshot("corr-004", 1) is None
        assert await store.load_snapshot("corr-004", 2) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_zero(self, store: RedisStateStore) -> None:
        count = await store.delete_snapshots("corr-none")
        assert count == 0


class TestKeyConstruction:
    """Key 构造测试。"""

    def test_make_key(self, store: RedisStateStore) -> None:
        key = store._make_key("corr-005", 3)
        assert key == "agentforge:snapshot:corr-005:3"


class TestTTL:
    """TTL 测试。"""

    @pytest.mark.asyncio
    async def test_custom_ttl(self, store: RedisStateStore) -> None:
        """自定义 TTL 不影响内存回退存储。"""
        await store.save_snapshot("corr-006", 1, {"x": 1}, ttl=100)
        loaded = await store.load_snapshot("corr-006", 1)
        assert loaded == {"x": 1}

    @pytest.mark.asyncio
    async def test_zero_ttl(self, store: RedisStateStore) -> None:
        """TTL 为 0 表示不过期。"""
        await store.save_snapshot("corr-007", 1, {"x": 1}, ttl=0)
        loaded = await store.load_snapshot("corr-007", 1)
        assert loaded == {"x": 1}
