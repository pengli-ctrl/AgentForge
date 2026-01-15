"""AgentForge 平台测试层：test_compose_config。

本测试模块验证 test_compose_config 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：test_platform_compose_contains_api_worker_and_migration。
"""

from pathlib import Path

import yaml


def test_platform_compose_contains_api_worker_and_migration() -> None:
    """验证 platform_compose_contains_api_worker_and_migration 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    path = Path("deploy/platform/docker-compose.platform.yml")
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = config["services"]
    assert "postgres" in services
    assert "temporal" in services
    assert "api" in services
    assert "worker" in services
    assert services["migrate"]["command"] == ["alembic", "upgrade", "head"]
    assert services["worker"]["command"] == ["python", "-m", "agentforge.platform.worker"]
