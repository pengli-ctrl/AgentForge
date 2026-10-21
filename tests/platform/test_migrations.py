"""测试模块。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_offline_migration_chain_contains_module_tables() -> None:
    """验证离线迁移包含模块对应的测试场景。"""
    env = dict(os.environ)
    env["AGENTFORGE_DATABASE_URL"] = (
        "postgresql+asyncpg://agentforge:agentforge@localhost:5432/agentforge"
    )
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE EXTENSION IF NOT EXISTS vector" in result.stdout
    assert "customer_id VARCHAR(64)" in result.stdout
    assert "published_at TIMESTAMP WITH TIME ZONE" in result.stdout
    assert "CREATE TABLE expense_claims" in result.stdout
    assert "CREATE TABLE tenant_modules" in result.stdout
    assert "CREATE SCHEMA IF NOT EXISTS module_support" in result.stdout
    assert "CREATE SCHEMA IF NOT EXISTS module_expense" in result.stdout
    assert "ALTER TABLE public.tickets SET SCHEMA module_support" in result.stdout
    assert "ALTER TABLE public.expense_claims SET SCHEMA module_expense" in result.stdout
    assert "CREATE TABLE module_expense.expense_attachments" in result.stdout
    assert "CREATE TABLE module_expense.expense_extractions" in result.stdout
    assert "CREATE TABLE module_expense.expense_ocr_jobs" in result.stdout
    assert "CREATE TABLE module_expense.expense_import_batches" in result.stdout
    assert "CREATE TABLE module_expense.expense_writeback_jobs" in result.stdout
    assert "CREATE TABLE module_expense.expense_invoices" in result.stdout
    assert "CREATE TABLE module_expense.expense_invoice_gate_alerts" in result.stdout
    assert "uq_expense_invoice_gate_alerts_active_key" in result.stdout
    assert "ADD COLUMN occurrence INTEGER" in result.stdout
    assert "ADD COLUMN assignee_id VARCHAR(64)" in result.stdout
    assert "CREATE TABLE upload_sessions" in result.stdout
    assert "CREATE TABLE outbox_handler_receipts" in result.stdout
    assert "CREATE TABLE module_asset_assets" in result.stdout
    assert "CREATE TABLE tenant_accounts" in result.stdout
    assert "CREATE TABLE usage_records" in result.stdout
