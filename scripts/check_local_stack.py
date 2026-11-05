"""检查本地集成服务健康状态。"""
import httpx

def check(url: str) -> None:
    """检查单个服务。

    Args:
        url: 服务地址。
    """
    response = httpx.get(url, timeout=5)
    response.raise_for_status()
    print(f"OK {url}")

if __name__ == "__main__":
    for target in ("http://localhost:8010/health", "http://localhost:8181/health", "http://localhost:4000/health"):
        check(target)
