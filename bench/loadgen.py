"""负载生成模块。"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

import httpx

# 请求构造器：base_url + method/path/body -> 发起并返回 (path, http_code, latency_s)
RequestFn = Callable[[httpx.AsyncClient, str], Awaitable[tuple[str, int, float]]]


def make_requests(
    clients: int,
    duration: float,
    fn: RequestFn,
    base_url: str,
) -> tuple[list[tuple[str, float]], list[str]]:
    """构造请求。

    Args:
        clients: 输入参数。
        duration: 执行持续时间。
        fn: 函数。
        base_url: 服务基础 URL。

    Returns:
        结果元组。
    """
    results: list[tuple[str, float]] = []
    errors: list[str] = []

    async def worker(client: httpx.AsyncClient) -> None:
        """执行工作进程。

        Args:
            client: 客户端实例。
        """
        deadline = time.monotonic() + duration
        path = "req"
        while True:
            if time.monotonic() >= deadline:
                break
            try:
                path, code, lat = await fn(client, base_url)
                results.append((path, lat))
                if code >= 500:
                    errors.append(f"{path}:{code}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{path}:{type(exc).__name__}")

    async def run() -> None:
        """运行任务。"""
        limits = httpx.Limits(max_connections=clients * 4, max_keepalive_connections=clients)
        async with httpx.AsyncClient(timeout=30.0, limits=limits) as client:
            await asyncio.gather(*(worker(client) for _ in range(clients)))

    asyncio.run(run())
    return results, errors


def percentile(sorted_lat: list[float], p: float) -> float:
    """计算百分位。

    Args:
        sorted_lat: 输入参数。
        p: 输入参数。

    Returns:
        数值结果。
    """
    if not sorted_lat:
        return 0.0
    k = (len(sorted_lat) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_lat) - 1)
    return sorted_lat[f] + (sorted_lat[c] - sorted_lat[f]) * (k - f)


@dataclass
class LadderResult:
    """梯度结果领域组件。

    Attributes:
        clients: 字段值。
        duration: 执行持续时间。
        reqs: 字段值。
        errors: 字段值。
        rps: 字段值。
        total_time: 总计。
        p50: 字段值。
        p90: 字段值。
        p95: 字段值。
        p99: 字段值。
        max_lat: 最大。
        error_rate: 错误速率。
    """

    clients: int
    duration: float
    reqs: int = 0
    errors: int = 0
    rps: float = 0.0
    total_time: float = 0.0
    p50: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    max_lat: float = 0.0
    error_rate: float = 0.0


def run_ladder(
    fn: RequestFn,
    base_url: str,
    clients_ladder: list[int],
    duration_per_step: float,
) -> list[LadderResult]:
    """运行梯度。

    Args:
        fn: 函数。
        base_url: 服务基础 URL。
        clients_ladder: 输入参数。
        duration_per_step: 步骤。

    Returns:
        结果列表。
    """
    out: list[LadderResult] = []
    for c in clients_ladder:
        t0 = time.monotonic()
        results, errors = make_requests(c, duration_per_step, fn, base_url)
        elp = time.monotonic() - t0
        lats = sorted(r[1] for r in results)
        reqs = len(results)
        rps = reqs / elp
        out.append(
            LadderResult(
                clients=c,
                duration=duration_per_step,
                reqs=reqs,
                errors=len(errors),
                rps=rps,
                total_time=elp,
                p50=percentile(lats, 50),
                p90=percentile(lats, 90),
                p95=percentile(lats, 95),
                p99=percentile(lats, 99),
                max_lat=lats[-1] if lats else 0.0,
                error_rate=(len(errors) / reqs * 100) if reqs else 0.0,
            )
        )
        print(
            f"  clients={c:>4}  reqs={reqs:>6}  rps={rps:7.1f}  "
            f"p50={out[-1].p50*1e3:6.1f}ms p90={out[-1].p90*1e3:6.1f}ms "
            f"p95={out[-1].p95*1e3:6.1f}ms p99={out[-1].p99*1e3:6.1f}ms "
            f"max={out[-1].max_lat*1e3:6.1f}ms err={out[-1].error_rate:5.2f}%"
        )
    return out


def _mp_worker_inline():
    """处理工作进程。"""
    import sys

    sys.path.insert(0, ".")
    import bench.loadgen as lg

    b, c, d, n = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    res, err = lg.make_requests(c, d, lg.choose_fn(n), b)
    print(len(res))
    if err:
        print(len(err), file=sys.stderr)


def run_ladder_mp(
    fn: RequestFn,
    base_url: str,
    clients_ladder: list[int],
    duration_per_step: float,
    processes: int = 4,
) -> list[LadderResult]:
    """多进程并发梯度压测：突破单进程客户端瓶颈，逼近服务端真实容量。

    Args:
        fn: 函数。
        base_url: 服务基础 URL。
        clients_ladder: 输入参数。
        duration_per_step: 步骤。
        processes: 输入参数。

    Returns:
        结果列表。
    """
    fn_name = next((k for k, v in REQUEST_FNS.items() if v == fn), "health")
    out: list[LadderResult] = []
    for c in clients_ladder:
        per = max(1, c // processes)
        t0 = time.monotonic()
        procs = []
        for _ in range(processes):
            p = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    _mp_worker_inline_code(),
                    base_url,
                    str(per),
                    str(duration_per_step),
                    fn_name,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            procs.append(p)
        total = 0
        for p in procs:
            try:
                o = p.stdout.read().decode().strip()
            except Exception:
                o = ""
            p.wait(timeout=duration_per_step + 60)
            try:
                total += int(o)
            except Exception:
                pass
        elp = time.monotonic() - t0
        rps = total / elp if elp else 0.0

        # 延迟补测：同一并发度下单进程一轮，取分位
        res, err = make_requests(c, duration_per_step, fn, base_url)
        lats = sorted(r[1] for r in res)
        out.append(
            LadderResult(
                clients=c,
                duration=duration_per_step,
                reqs=total,
                errors=len(err),
                rps=rps,
                total_time=elp,
                p50=percentile(lats, 50),
                p90=percentile(lats, 90),
                p95=percentile(lats, 95),
                p99=percentile(lats, 99),
                max_lat=lats[-1] if lats else 0.0,
                error_rate=(len(err) / len(res) * 100) if res else 0.0,
            )
        )
        print(
            f"  clients={c:>4} (x{processes}p)  reqs={total:>6}  rps={rps:7.1f}  "
            f"p50={out[-1].p50*1e3:6.1f}ms p90={out[-1].p90*1e3:6.1f}ms "
            f"p99={out[-1].p99*1e3:6.1f}ms err={out[-1].error_rate:5.2f}%"
        )
    return out


def _mp_worker_inline_code() -> str:
    """返回多进程工作进程执行的内联代码。

    Returns:
        字符串结果。
    """
    return (
        "import sys;sys.path.insert(0,'.');"
        "import bench.loadgen as lg;"
        "b,c,d,n=sys.argv[1],int(sys.argv[2]),float(sys.argv[3]),sys.argv[4];"
        "res,err=lg.make_requests(c,d,lg.choose_fn(n),b);"
        "print(len(res));"
        "print(len(err),file=sys.stderr)"
    )


def dump_json(results: list[LadderResult], path: str) -> None:
    """导出JSON。

    Args:
        results: 待处理或待保存的结果。
        path: 文件或资源路径。
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump([r.__dict__ for r in results], f, ensure_ascii=False, indent=2)


async def bench_health(client: httpx.AsyncClient, base_url: str) -> tuple[str, int, float]:
    """执行基准测试健康。

    Args:
        client: 客户端实例。
        base_url: 服务基础 URL。

    Returns:
        结果元组。
    """
    t0 = time.monotonic()
    r = await client.get(f"{base_url}/health/live")
    return ("/health/live", r.status_code, time.monotonic() - t0)


async def bench_overview(client: httpx.AsyncClient, base_url: str) -> tuple[str, int, float]:
    """执行基准测试总览。

    Args:
        client: 客户端实例。
        base_url: 服务基础 URL。

    Returns:
        结果元组。
    """
    t0 = time.monotonic()
    r = await client.get(f"{base_url}/v1/console/overview?tenant_id=tenant-a")
    return ("/v1/console/overview", r.status_code, time.monotonic() - t0)


async def bench_dashboard(client: httpx.AsyncClient, base_url: str) -> tuple[str, int, float]:
    """执行基准测试看板。

    Args:
        client: 客户端实例。
        base_url: 服务基础 URL。

    Returns:
        结果元组。
    """
    t0 = time.monotonic()
    r = await client.get(f"{base_url}/v1/console/dashboard?tenant_id=tenant-a")
    return ("/v1/console/dashboard", r.status_code, time.monotonic() - t0)


REQUEST_FNS = {
    "health": bench_health,
    "overview": bench_overview,
    "dashboard": bench_dashboard,
}


def choose_fn(name: str) -> RequestFn:
    """选择函数。

    Args:
        name: 资源或对象名称。

    Returns:
        请求函数结果。

    Raises:
        KeyError: 缺少必要配置或目标对象时抛出。
    """
    if name not in REQUEST_FNS:
        raise KeyError(f"unknown request fn: {name}; choose from {list(REQUEST_FNS)}")
    return REQUEST_FNS[name]


if __name__ == "__main__":
    print("loadgen module OK")
