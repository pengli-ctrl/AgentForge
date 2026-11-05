"""测试 Redis ContextStore 适配。"""

import pytest

from agentforge.platform.infrastructure.context_store import RedisContextStore, build_context_store
from agentforge.platform.settings import Settings


class FakeRedis:
    """提供测试用 Redis 行为。"""

    def __init__(self):
        """初始化内存哈希和列表。"""
        self.hashes = {}
        self.lists = {}

    async def delete(self, *keys):
        """删除测试键。

        Args:
            *keys: 待删除键。
        """
        for key in keys:
            self.hashes.pop(key, None)
            self.lists.pop(key, None)

    async def hset(self, key, field=None, value=None, mapping=None):
        """写入哈希字段。

        Args:
            key: 键。
            field: 字段。
            value: 字段值。
            mapping: 批量字段。
        """
        self.hashes.setdefault(key, {})
        if mapping:
            self.hashes[key].update(mapping)
        else:
            self.hashes[key][field] = value

    async def hget(self, key, field):
        """读取哈希字段。

        Args:
            key: 键。
            field: 字段。

        Returns:
            字段值。
        """
        return self.hashes.get(key, {}).get(field)

    async def hgetall(self, key):
        """读取全部哈希字段。

        Args:
            key: 键。

        Returns:
            字段字典。
        """
        return dict(self.hashes.get(key, {}))

    async def hexists(self, key, field):
        """判断字段存在。

        Args:
            key: 键。
            field: 字段。

        Returns:
            是否存在。
        """
        return field in self.hashes.get(key, {})

    async def hdel(self, key, field):
        """删除哈希字段。

        Args:
            key: 键。
            field: 字段。

        Returns:
            删除数量。
        """
        existed = field in self.hashes.get(key, {})
        self.hashes.get(key, {}).pop(field, None)
        return int(existed)

    async def hlen(self, key):
        """读取哈希长度。

        Args:
            key: 键。

        Returns:
            长度。
        """
        return len(self.hashes.get(key, {}))

    async def expire(self, key, seconds):
        """模拟设置过期时间。

        Args:
            key: 键。
            seconds: 秒数。

        Returns:
            是否成功。
        """
        return True

    async def rpush(self, key, value):
        """追加列表元素。

        Args:
            key: 键。
            value: 值。
        """
        self.lists.setdefault(key, []).append(value)

    async def lrange(self, key, start, end):
        """读取列表范围。

        Args:
            key: 键。
            start: 起始位置。
            end: 结束位置。

        Returns:
            元素列表。
        """
        return list(self.lists.get(key, []))


@pytest.mark.asyncio
async def test_redis_context_store_round_trip() -> None:
    """验证 Redis ContextStore 读写。"""
    store = RedisContextStore(FakeRedis(), ttl_seconds=30)
    await store.initialize({"input": "x"})
    await store.write("node1", {"answer": 42})
    assert await store.read("node1") == {"answer": 42}
    assert (await store.read_with_mapping({"value": "$ctx.node1"}))["value"] == {"answer": 42}
    assert await store.has("node1") is True
    await store.log_access("node1", ["node1"])
    assert (await store.get_access_log())[0]["node_id"] == "node1"


def test_context_store_factory_defaults_to_memory() -> None:
    """验证默认使用内存 ContextStore。"""
    store = build_context_store(Settings(_env_file=None))
    assert store.__class__.__name__ == "ContextStore"
