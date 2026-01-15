"""P1-1 压测 · 一键运行器（多进程负载生成，规避客户端单进程瓶颈）。

流程：
1. 用 uvicorn 启动 bench 应用（内存容器 + 预置数据，关闭鉴权）到 PORT。
2. 等待 /health/ready。
3. 对三个代表性端点各跑一遍多进程并发梯度（吞吐 + 延迟分位）。
4. 原始数据落 bench/results_*.json，并打印汇总表供写报告。

无需任何外部压测工具（k6/locust）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bench.loadgen import choose_fn, run_ladder_mp  # noqa: E402

PORT = 8123
BASE = f"http://127.0.0.1:{PORT}"
WARMUP = 2.0
STEP_DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
CLIENTS = [1, 10, 25, 50, 100]
PROCESSES = 4
OUT_DIR = "bench"

ENDPOINTS = ["health", "overview", "dashboard"]


def wait_ready(timeout: float = 60.0) -> bool:
    """执行 wait_ready 对应的逻辑，并返回处理结果。

    Args:
        timeout: float，调用方传入的 timeout 参数。

    Returns:
        bool，函数执行后的结果。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = httpx.get(BASE + "/health/ready", timeout=3.0)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> None:
    """作为程序入口，解析参数并启动对应流程。

    Returns:
        None，函数执行后的结果。
    """
    print(f"[1/4] 启动 uvicorn ({PORT}) ...")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "bench.platform_bench_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
    )
    try:
        if not wait_ready():
            print("  服务未就绪，退出。")
            proc.kill()
            sys.exit(1)
        print("  就绪。")
        time.sleep(WARMUP)

        for name in ENDPOINTS:
            print(f"\n[2/4] 压测端点: {name}")
            results = run_ladder_mp(
                choose_fn(name), BASE, CLIENTS, STEP_DURATION, processes=PROCESSES
            )
            with open(f"{OUT_DIR}/results_{name}.json", "w", encoding="utf-8") as fp:
                json.dump([r.__dict__ for r in results], fp, ensure_ascii=False, indent=2)
            print(f"  已保存 {OUT_DIR}/results_{name}.json")
    finally:
        print("\n[3/4] 停止 uvicorn ...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    print("[4/4] 完成。")


if __name__ == "__main__":
    main()
