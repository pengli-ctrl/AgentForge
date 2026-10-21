"""平台应用模块。"""

from __future__ import annotations

import asyncio
import datetime

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.api.security import ApiKeyAuthenticator
from agentforge.platform.application.builtin_policies import seed_rbac
from agentforge.platform.domain.cost import CostRecord
from agentforge.platform.domain.tenant_quota import TenantQuota
from agentforge.platform.runtime import build_memory_container


def _day(offset: int) -> datetime.datetime:
    """返回相对当前 UTC 日期偏移后的日期边界。

    Args:
        offset: 分页偏移量。

    Returns:
        处理结果对象。
    """
    d = datetime.datetime.now(datetime.timezone.utc)
    return d - datetime.timedelta(days=offset)


async def seed(container) -> None:
    """初始化初始数据。

    Args:
        container: 服务容器。
    """
    await seed_rbac(container.rbac_repository)
    await seed_rbac(container.high_risk_authorizer._rbac_repository)

    await container.tenant_quota_repository.upsert(
        TenantQuota(
            tenant_id="tenant-a",
            monthly_limit=1000.0,
            hard_limit=1.0,
            warning_threshold=0.8,
        )
    )

    for i in range(20):
        await container.cost_repository.save(
            CostRecord(
                tenant_id="tenant-a",
                task_id=f"task-{i}",
                model_name="qwen3-pro",
                provider="dashscope",
                input_tokens=200 + i * 10,
                output_tokens=50 + i,
                amount=round(0.001 + i * 0.0005, 6),
                created_at=_day(i % 3),
            )
        )


async def _build():
    """构建对象。

    Returns:
        处理结果。
    """
    container = build_memory_container(
        authenticator=ApiKeyAuthenticator(enabled=False),
    )
    await seed(container)
    return create_platform_app(container)


def _run(coro):
    """在独立线程的专用事件循环里执行协程。

    Args:
        coro: 输入参数。

    Returns:
        处理结果。

    Raises:
        result['error']: 操作无法完成时抛出。
    """
    import threading

    result: dict = {}

    def _target():
        """处理目标。"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result["value"] = loop.run_until_complete(coro)
        except BaseException as exc:  # noqa: BLE001
            result["error"] = exc
        finally:
            loop.close()

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join()
    if "error" in result:
        raise result["error"]
    return result["value"]


def create_bench_app():
    """创建应用。

    Returns:
        处理结果。
    """
    return _run(_build())


app = create_bench_app()
