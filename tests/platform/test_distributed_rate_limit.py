"""测试分布式限流后端。"""

import pytest

from agentforge.platform.infrastructure.rate_limit import (
    InMemoryRateLimitBackend,
    ValkeyRateLimitBackend,
    build_rate_limit_backend,
)
from agentforge.platform.settings import Settings


class FakeValkey:
    """提供测试用 Valkey 脚本执行器。"""

    def __init__(self, values):
        """初始化预置返回值。

        Args:
            values: 预置脚本结果。
        """
        self.values = list(values)
        self.calls = []

    async def eval(self, *args, **kwargs):
        """模拟脚本执行。

        Args:
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            预置脚本结果。
        """
        self.calls.append((args, kwargs))
        return self.values.pop(0)


@pytest.mark.asyncio
async def test_memory_rate_limit_rejects_over_capacity() -> None:
    """验证内存限流会拒绝超限请求。"""
    backend = InMemoryRateLimitBackend(capacity=1, refill_per_second=0.0001)
    assert (await backend.acquire("t1:route")).allowed is True
    assert (await backend.acquire("t1:route")).allowed is False


@pytest.mark.asyncio
async def test_valkey_rate_limit_uses_shared_counter() -> None:
    """验证 Valkey 限流使用共享计数。"""
    from agentforge.platform.infrastructure.valkey_coordination import ValkeyCoordination

    fake = FakeValkey([[1, 90000, 0], [0, 0, 250]])
    backend = ValkeyRateLimitBackend(ValkeyCoordination(fake), capacity=100, refill_per_second=10)
    assert (await backend.acquire("tenant:a:module:support")).allowed is True
    denied = await backend.acquire("tenant:a:module:support")
    assert denied.allowed is False
    assert denied.retry_after_ms == 250
    assert len(fake.calls) == 2


def test_rate_limit_factory_rejects_unknown_backend() -> None:
    """验证未知限流后端被拒绝。

    Raises:
        AssertionError: 未抛出预期异常时抛出。
    """
    try:
        build_rate_limit_backend(Settings(_env_file=None, rate_limit_backend="bad"))
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("expected ValueError")
