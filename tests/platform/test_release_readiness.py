"""测试释放就绪状态测试模块。"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import yaml

from scripts import build_private_release, build_wheel
from scripts.verify_release import verify

ROOT = Path(__file__).resolve().parents[2]


def test_release_metadata_version_and_ci_gate_are_consistent() -> None:
    """验证释放元数据版本及门禁为一致对应的测试场景。"""
    report = verify()
    assert report["ok"] is True, report["errors"]
    assert report["version"] == "3.1.0"
    assert report["migration_head"] == "20261021_0032"
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert {"lint", "test", "syntax-check", "infra", "security", "release", "build"} <= set(
        workflow["jobs"]
    )


def test_dockerfile_uses_platform_app_and_non_root_runtime() -> None:
    """验证使用平台应用及非根运行时对应的测试场景。"""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "agentforge.platform.api.app:create_platform_app" in dockerfile
    assert "/health/live" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "AGENTFORGE_HOME=/app" in dockerfile


def test_wheel_build_is_reproducible(tmp_path: Path) -> None:
    """验证构建是否可复现对应的测试场景。

    Args:
        tmp_path: 路径。
    """
    first_wheel, _ = build_wheel.build(tmp_path / "first")
    second_wheel, _ = build_wheel.build(tmp_path / "second")
    assert first_wheel.read_bytes() == second_wheel.read_bytes()
    assert first_wheel.name == "agentforge-3.1.0-py3-none-any.whl"


def test_private_package_build_is_reproducible(tmp_path: Path) -> None:
    """验证构建是否可复现对应的测试场景。

    Args:
        tmp_path: 路径。
    """
    first_archive, first_checksum = build_private_release.build(tmp_path / "first")
    second_archive, _ = build_private_release.build(tmp_path / "second")
    assert first_archive.read_bytes() == second_archive.read_bytes()
    expected = hashlib.sha256(first_archive.read_bytes()).hexdigest()
    assert expected in first_checksum.read_text(encoding="utf-8")


def test_baseline_docs_keep_scope_and_working_links() -> None:
    """验证当前文档集合保持商业基线边界，且不再引用已删除的运维文档。"""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    private_delivery = (ROOT / "docs/security/PRIVATE_DELIVERY.md").read_text(encoding="utf-8")
    assert "商业基线" in readme
    assert "不承诺生产 HA" in readme
    assert "不是生产运行手册" in private_delivery
    removed = (
        "docs/release/",
        "PRIVATE_DEPLOYMENT_RUNBOOK.md",
        "SECURITY_CHECKLIST.md",
        "PRODUCTION_INTEGRATION.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "README.en.md",
    )
    for document in (ROOT / "README.md", ROOT / "SECURITY.md"):
        text = document.read_text(encoding="utf-8")
        for marker in removed:
            assert marker not in text


def test_offline_upgrade_and_rollback_sql_from_previous_release() -> None:
    """验证离线升级及回滚SQL从上一个释放对应的测试场景。"""
    env = dict(os.environ)
    env["AGENTFORGE_DATABASE_URL"] = (
        "postgresql+asyncpg://agentforge:agentforge@localhost:5432/agentforge"
    )
    env["PYTHONIOENCODING"] = "utf-8"
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "20261020_0028:head", "--sql"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    downgrade = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "downgrade",
            "20261021_0032:20261020_0028",
            "--sql",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert upgrade.returncode == 0, upgrade.stderr
    assert downgrade.returncode == 0, downgrade.stderr
    assert "CREATE TABLE tenant_accounts" in upgrade.stdout
    assert "CREATE TABLE usage_records" in upgrade.stdout
    assert "DROP TABLE outbox_handler_receipts" in downgrade.stdout
    assert "ALTER TABLE tenant_modules DROP COLUMN config_values" in downgrade.stdout
