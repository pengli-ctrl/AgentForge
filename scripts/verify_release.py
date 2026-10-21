"""校验释放模块。"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HEAD = "20261021_0032"


def _version() -> str:
    """执行版本。

    Returns:
        字符串结果。

    Raises:
        ValueError: 输入值或业务状态不合法时抛出。
    """
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', text, re.MULTILINE)
    if not match:
        raise ValueError("pyproject project.version not found")
    return match.group(1)


def _migration_head() -> str:
    """处理迁移。

    Returns:
        字符串结果。

    Raises:
        ValueError: 输入值或业务状态不合法时抛出。
    """
    revisions: dict[str, str | None] = {}
    referenced: set[str] = set()
    for path in (ROOT / "alembic" / "versions").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        revision = re.search(r'^revision = "([^"]+)"', text, re.MULTILINE)
        down = re.search(r'^down_revision = (?:"([^"]+)"|None)', text, re.MULTILINE)
        if not revision:
            continue
        parent = down.group(1) if down and down.group(1) else None
        revisions[revision.group(1)] = parent
        if parent:
            referenced.add(parent)
    heads = sorted(set(revisions) - referenced)
    if len(heads) != 1:
        raise ValueError(f"expected one migration head, got {heads}")
    return heads[0]


def verify() -> dict[str, object]:
    """校验结果。

    Returns:
        结构化结果字典。
    """
    version = _version()
    checks: list[str] = []
    errors: list[str] = []

    expected_files = {
        "package": (ROOT / "agentforge" / "__init__.py", f'__version__ = "{version}"'),
        "platform_app": (
            ROOT / "agentforge" / "platform" / "api" / "app.py",
            "version=__version__",
        ),
        "legacy_app": (ROOT / "agentforge" / "api" / "app.py", "version=__version__"),
        "helm_chart": (
            ROOT / "deploy" / "helm" / "agentforge" / "Chart.yaml",
            f'appVersion: "{version}"',
        ),
        "helm_values": (
            ROOT / "deploy" / "helm" / "agentforge" / "values.yaml",
            f'tag: "{version}"',
        ),
        "dockerfile": (ROOT / "Dockerfile", "agentforge.platform.api.app:create_platform_app"),
        "healthcheck": (ROOT / "Dockerfile", "/health/live"),
    }
    for name, (path, needle) in expected_files.items():
        if not path.exists():
            errors.append(f"{name}: missing {path.relative_to(ROOT)}")
        elif needle not in path.read_text(encoding="utf-8"):
            errors.append(f"{name}: missing marker {needle!r}")
        else:
            checks.append(name)

    try:
        head = _migration_head()
    except ValueError as exc:
        errors.append(str(exc))
        head = ""
    if head == EXPECTED_HEAD:
        checks.append("migration_head")
    else:
        errors.append(f"unexpected migration head: {head}")

    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for job in ("lint:", "test:", "syntax-check:", "infra:", "security:", "release:"):
        if job in ci:
            checks.append(f"ci:{job[:-1]}")
        else:
            errors.append(f"CI job missing: {job[:-1]}")

    return {
        "version": version,
        "migration_head": head,
        "checks": checks,
        "errors": errors,
        "ok": not errors,
    }


def main() -> None:
    """执行主流程。

    Raises:
        SystemExit: 操作无法完成时抛出。
    """
    report = verify()
    output = ROOT / "dist" / "release-verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
