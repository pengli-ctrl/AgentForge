"""运行模块。"""

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
    """等待就绪。

    Args:
        timeout: 操作超时时间。

    Returns:
        操作是否成功。
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
    """执行主流程。"""
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
