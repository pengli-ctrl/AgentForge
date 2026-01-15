"""P1-1 压测 · 平台应用启动模块（内存容器 + 预置数据，不依赖任何外部服务）。

同时支持 uvicorn 两种加载方式：
  single / default : ``uvicorn bench.platform_bench_app:app``
  multi-worker     : ``uvicorn bench.platform_bench_app:create_bench_app --factory --workers N``

数据全部落在内存 repo，保证可复现、可上 GitHub、无外部依赖。
构建用「独立事件循环」执行，避免 Windows spawn 子进程 + asyncio.run 冲突。
"""

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
    """执行 _day 对应的逻辑，并返回处理结果。

    Args:
        offset: int，调用方传入的 offset 参数。

    Returns:
        datetime.datetime，函数执行后的结果。
    """
    d = datetime.datetime.now(datetime.timezone.utc)
    return d - datetime.timedelta(days=offset)


async def seed(container) -> None:
    """预置少量真实数据，让 /v1/console/* 与 /v1/costs/* 返回非空结果。"""
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
    """执行 _build 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
    container = build_memory_container(
        authenticator=ApiKeyAuthenticator(enabled=False),
    )
    await seed(container)
    return create_platform_app(container)


def _run(coro):
    """在独立线程的专用事件循环里执行协程。

    规避两个坑：
    - uvicorn --workers 在 Windows 用 spawn 起子进程，导入本模块时主线程已在运行
      事件循环，任何在同一线程再跑 loop 都会触发
      ``Cannot run the event loop while another loop is running``。
    - 将 async 构建放在独立线程 + 独立 loop，通过 run_coroutine_threadsafe 取结果，
      与 uvicorn 的事件循环彻底隔离。
    """
    import threading

    result: dict = {}

    def _target():
        """执行 _target 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
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
    """uvicorn --factory 入口：每次调用独立构建（支持 --workers）。"""
    return _run(_build())


app = create_bench_app()
