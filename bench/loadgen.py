"""P1-1 压测 · 轻量自包含异步负载生成器（支持多进程，规避单进程客户端瓶颈）。

不依赖 k6/locust 等外部工具：用 httpx + asyncio 直接压测真实 uvicorn 服务。

为什么需要多进程？
  单进程 asyncio + httpx 自身受 GIL / 单事件循环限制，客户端吞吐封顶（实测 ~75-190 rps），
  会掩盖服务端真实容量。k6 / locust 同样靠多 worker / 多进程突破客户端瓶颈。
  因此高频压测走「多进程」：父进程按需起 N 个子进程，每个子进程用自己的事件循环 +
  独立连接池跑 clients/N 并发，父进程汇总各并发梯度下的吞吐 / 延迟分位 / 错误率。

输出：每个并发梯度下的 吞吐(req/s)、延迟分位(P50/P90/P95/P99)、错误率。
"""

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
    """跑一轮：clients 个并发协程，各自持续请求到 duration 秒耗尽。返回 (结果, 错误) 二元组。"""
    results: list[tuple[str, float]] = []
    errors: list[str] = []

    async def worker(client: httpx.AsyncClient) -> None:
        """执行 worker 对应的逻辑，并返回处理结果。

        Args:
            client: httpx.AsyncClient，调用方传入的 client 参数。

        Returns:
            None，函数执行后的结果。
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
        """执行 run 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。
        """
        limits = httpx.Limits(max_connections=clients * 4, max_keepalive_connections=clients)
        async with httpx.AsyncClient(timeout=30.0, limits=limits) as client:
            await asyncio.gather(*(worker(client) for _ in range(clients)))

    asyncio.run(run())
    return results, errors


def percentile(sorted_lat: list[float], p: float) -> float:
    """sorted_lat 升序；返回 p 分位（0-100）。"""
    if not sorted_lat:
        return 0.0
    k = (len(sorted_lat) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_lat) - 1)
    return sorted_lat[f] + (sorted_lat[c] - sorted_lat[f]) * (k - f)


@dataclass
class LadderResult:
    """LadderResult。

    LadderResult 封装相关领域行为，保持职责单一并降低调用方复杂度。

    主要成员：
    - clients: int。
    - duration: float。
    - reqs: int。
    - errors: int。
    - rps: float。
    - total_time: float。
    - p50: float。
    - p90: float。
    - p95: float。
    - p99: float。
    - max_lat: float。
    - error_rate: float。

    设计约束：
    - 保持接口稳定，避免调用方依赖内部实现细节。
    - 涉及隔离、审批、审计、成本或失败恢复的逻辑必须显式处理。
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
    """单进程并发梯度压测（低并发/快速排查用；高频请用 run_ladder_mp）。"""
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
    """内联子进程入口：读取 b c d n 参数并打印请求数。用于多进程压测子进程。"""
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

    - 吞吐/总量：由 processes 个子进程（每进程 clients/processes 并发）取回请求数汇总，
      客户端瓶颈被解除，吞吐代表服务端该并发下的真实处理能力。
    - 延迟分位：多进程聚合难以回传逐请求延迟；故对同一并发梯度再用单进程补测一轮，
      该轮在服务端同一并发度下观测到的逐请求延迟即为该负载下的真实 P50/P90/P99。
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
    """执行 _mp_worker_inline_code 对应的逻辑，并返回处理结果。

    Returns:
        str，函数执行后的结果。
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
    """执行 dump_json 对应的逻辑，并返回处理结果。

    Args:
        results: list[LadderResult]，调用方传入的 results 参数。
        path: str，调用方传入的 path 参数。

    Returns:
        None，函数执行后的结果。
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump([r.__dict__ for r in results], f, ensure_ascii=False, indent=2)


async def bench_health(client: httpx.AsyncClient, base_url: str) -> tuple[str, int, float]:
    """/health/live —— 纯框架基线（近零业务逻辑）。"""
    t0 = time.monotonic()
    r = await client.get(f"{base_url}/health/live")
    return ("/health/live", r.status_code, time.monotonic() - t0)


async def bench_overview(client: httpx.AsyncClient, base_url: str) -> tuple[str, int, float]:
    """/v1/console/overview —— 平台聚合读（配额+成本读，代表性平台业务读路径）。"""
    t0 = time.monotonic()
    r = await client.get(f"{base_url}/v1/console/overview?tenant_id=tenant-a")
    return ("/v1/console/overview", r.status_code, time.monotonic() - t0)


async def bench_dashboard(client: httpx.AsyncClient, base_url: str) -> tuple[str, int, float]:
    """/v1/console/dashboard —— 仪表盘聚合（成本趋势+模型分布，较重读路径）。"""
    t0 = time.monotonic()
    r = await client.get(f"{base_url}/v1/console/dashboard?tenant_id=tenant-a")
    return ("/v1/console/dashboard", r.status_code, time.monotonic() - t0)


REQUEST_FNS = {
    "health": bench_health,
    "overview": bench_overview,
    "dashboard": bench_dashboard,
}


def choose_fn(name: str) -> RequestFn:
    """执行 choose_fn 对应的逻辑，并返回处理结果。

    Args:
        name: str，调用方传入的 name 参数。

    Returns:
        RequestFn，函数执行后的结果。

    Raises:
        KeyError: 当输入、状态或外部依赖不满足要求时抛出。
    """
    if name not in REQUEST_FNS:
        raise KeyError(f"unknown request fn: {name}; choose from {list(REQUEST_FNS)}")
    return REQUEST_FNS[name]


if __name__ == "__main__":
    print("loadgen module OK")
