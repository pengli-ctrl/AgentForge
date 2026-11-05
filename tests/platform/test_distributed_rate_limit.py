import pytest

from agentforge.platform.infrastructure.rate_limit import InMemoryRateLimitBackend, ValkeyRateLimitBackend, build_rate_limit_backend
from agentforge.platform.settings import Settings


class FakeValkey:
    def __init__(self, values):
        self.values = list(values)
        self.calls = []
    async def eval(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.values.pop(0)


@pytest.mark.asyncio
async def test_memory_rate_limit_rejects_over_capacity() -> None:
    backend = InMemoryRateLimitBackend(capacity=1, refill_per_second=0.0001)
    assert (await backend.acquire("t1:route")).allowed is True
    second = await backend.acquire("t1:route")
    assert second.allowed is False


@pytest.mark.asyncio
async def test_valkey_rate_limit_uses_shared_counter() -> None:
    fake = FakeValkey([[1, 90000, 0], [0, 0, 250]])
    from agentforge.platform.infrastructure.valkey_coordination import ValkeyCoordination
    backend = ValkeyRateLimitBackend(ValkeyCoordination(fake), capacity=100, refill_per_second=10)
    assert (await backend.acquire("tenant:a:module:support")).allowed is True
    denied = await backend.acquire("tenant:a:module:support")
    assert denied.allowed is False
    assert denied.retry_after_ms == 250
    assert len(fake.calls) == 2


def test_rate_limit_factory_rejects_unknown_backend() -> None:
    try:
        build_rate_limit_backend(Settings(_env_file=None, rate_limit_backend="bad"))
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("expected ValueError")
