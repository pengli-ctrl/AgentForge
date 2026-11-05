import pytest

from agentforge.platform.infrastructure.context_store import RedisContextStore, build_context_store
from agentforge.platform.settings import Settings


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.lists = {}
    async def delete(self, *keys):
        for key in keys: self.hashes.pop(key, None); self.lists.pop(key, None)
    async def hset(self, key, field=None, value=None, mapping=None):
        self.hashes.setdefault(key, {})
        if mapping: self.hashes[key].update(mapping)
        else: self.hashes[key][field] = value
    async def hget(self, key, field): return self.hashes.get(key, {}).get(field)
    async def hgetall(self, key): return dict(self.hashes.get(key, {}))
    async def hexists(self, key, field): return field in self.hashes.get(key, {})
    async def hdel(self, key, field):
        existed = field in self.hashes.get(key, {})
        self.hashes.get(key, {}).pop(field, None)
        return int(existed)
    async def hlen(self, key): return len(self.hashes.get(key, {}))
    async def expire(self, key, seconds): return True
    async def rpush(self, key, value): self.lists.setdefault(key, []).append(value)
    async def lrange(self, key, start, end): return list(self.lists.get(key, []))


@pytest.mark.asyncio
async def test_redis_context_store_round_trip() -> None:
    store = RedisContextStore(FakeRedis(), ttl_seconds=30)
    await store.initialize({"input": "x"})
    await store.write("node1", {"answer": 42})
    assert await store.read("node1") == {"answer": 42}
    assert (await store.read_with_mapping({"value": "$ctx.node1"}))["value"] == {"answer": 42}
    assert await store.has("node1") is True
    await store.log_access("node1", ["node1"])
    assert (await store.get_access_log())[0]["node_id"] == "node1"


def test_context_store_factory_defaults_to_memory() -> None:
    store = build_context_store(Settings(_env_file=None))
    assert store.__class__.__name__ == "ContextStore"
