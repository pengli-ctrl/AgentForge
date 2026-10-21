"""测试模块。"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


def _walk(value, path=""):
    """遍历数据。

    Args:
        value: 待处理值。
        path: 文件或资源路径。

    Yields:
        逐次生成的结果。
    """
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, path
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child, path)


def test_helm_chart_uses_external_secret_and_hardened_container_defaults() -> None:
    """验证使用外部密钥及容器默认项对应的测试场景。"""
    root = Path("deploy/helm/agentforge")
    chart = yaml.safe_load((root / "Chart.yaml").read_text(encoding="utf-8"))
    values = yaml.safe_load((root / "values.yaml").read_text(encoding="utf-8"))
    assert chart["apiVersion"] == "v2"
    assert values["existingSecret"] == "agentforge-secrets"
    sensitive = [
        key
        for key, path in _walk(values)
        if re.search(r"(password|token|api[_-]?key|private[_-]?key)", key, re.IGNORECASE)
    ]
    assert sensitive == []
    templates = "".join(
        path.read_text(encoding="utf-8") for path in (root / "templates").glob("*.yaml")
    )
    assert "kind: Secret" not in templates
    assert "secretRef:" in templates
    assert "runAsNonRoot: true" in (root / "values.yaml").read_text(encoding="utf-8")
    assert "readOnlyRootFilesystem: true" in (root / "values.yaml").read_text(encoding="utf-8")
    assert 'command: ["alembic", "upgrade", "head"]' in templates


def test_security_checklist_and_runbook_cover_required_controls() -> None:
    """验证安全及必需对应的测试场景。"""
    checklist = Path("docs/security/SECURITY_CHECKLIST.md").read_text(encoding="utf-8")
    runbook = Path("docs/security/PRIVATE_DEPLOYMENT_RUNBOOK.md").read_text(encoding="utf-8")
    for required in ("租户隔离", "Webhook", "Secret", "PII", "审计", "密钥", "OIDC"):
        assert required in checklist
    required_commands = (
        "helm upgrade",
        "pg_dump",
        "pg_restore",
        "helm rollback",
        "AGENTFORGE_RESTORE_CONFIRM",
    )
    for required in required_commands:
        assert required in runbook
    backup = Path("scripts/backup_private.sh").read_text(encoding="utf-8")
    restore = Path("scripts/restore_private.sh").read_text(encoding="utf-8")
    assert "pg_dump" in backup and "sha256sum" in backup
    assert "AGENTFORGE_RESTORE_CONFIRM" in restore and "pg_restore" in restore


def test_security_docs_do_not_embed_literal_tenant_keys() -> None:
    """验证安全文档执行不向量化租户键对应的测试场景。"""
    for path in Path("docs/security").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"tenant-key-[A-Za-z0-9]{8,}", text)
        assert "<generated>" in text or path.name == "SECURITY_CHECKLIST.md"
