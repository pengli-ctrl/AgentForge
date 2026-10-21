"""共享测试夹具测试模块。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_INFRA = os.environ.get("AGENTFORGE_RUN_INFRA_TESTS", "").lower() in {"1", "true", "yes"}
DATABASE_URL = os.environ.get(
    "AGENTFORGE_INFRA_DATABASE_URL",
    "postgresql+asyncpg://agentforge:agentforge@localhost:5432/agentforge_test",
)

pytestmark = [
    pytest.mark.infra,
    pytest.mark.skipif(not RUN_INFRA, reason="set AGENTFORGE_RUN_INFRA_TESTS=1"),
]


def _alembic(action: str) -> None:
    """处理Alembic 迁移。

    Args:
        action: 待执行动作名称。
    """
    env = dict(os.environ)
    env["AGENTFORGE_DATABASE_URL"] = DATABASE_URL
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", action, "head" if action == "upgrade" else "base"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """处理迁移后的数据库。

    Yields:
        逐次生成的结果。
    """
    if not RUN_INFRA:
        yield
        return
    _alembic("upgrade")
    yield


def run_migration_round_trip() -> None:
    """运行迁移轮次往返。"""
    _alembic("downgrade")
    _alembic("upgrade")
