"""迁移模块。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_RELEASE_REVISION = "20261020_0028"


def alembic(database_url: str, *args: str) -> str:
    """处理Alembic 迁移。

    Args:
        database_url: 数据库URL。
        args: 位置参数。

    Returns:
        字符串结果。

    Raises:
        RuntimeError: 运行时依赖或状态不满足要求时抛出。
    """
    env = dict(os.environ)
    env["AGENTFORGE_DATABASE_URL"] = database_url
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def main() -> None:
    """执行主流程。

    Raises:
        SystemExit: 操作无法完成时抛出。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-url", default=os.environ.get("AGENTFORGE_MIGRATION_DRILL_DATABASE_URL", "")
    )
    parser.add_argument("--from-revision", default=PREVIOUS_RELEASE_REVISION)
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("set AGENTFORGE_MIGRATION_DRILL_DATABASE_URL")
    if os.environ.get("AGENTFORGE_MIGRATION_DRILL_CONFIRM") != "agentforge":
        raise SystemExit("set AGENTFORGE_MIGRATION_DRILL_CONFIRM=agentforge")
    if (
        "test" not in args.database_url.lower()
        and os.environ.get("AGENTFORGE_ALLOW_NON_TEST_DRILL") != "true"
    ):
        raise SystemExit("migration drill database URL must contain 'test'")
    steps = []
    for action, revision in (
        ("upgrade", args.from_revision),
        ("upgrade", "head"),
        ("downgrade", args.from_revision),
        ("upgrade", "head"),
    ):
        output = alembic(args.database_url, action, revision)
        steps.append({"action": action, "revision": revision, "output": output})
    report = {"ok": True, "database_url": args.database_url, "steps": steps}
    output = ROOT / "dist" / "migration-drill.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
