"""测试报销策略测试模块。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.modules.expense.domain.policy import ExpensePolicy
from agentforge.platform.settings import get_settings


def test_expense_policy_flags_category_and_budget() -> None:
    """验证报销策略标记及预算对应的测试场景。"""
    policy = ExpensePolicy.from_config(
        {
            "category_limits": "meal=5000,travel=100000",
            "monthly_budget_cents": 10000,
        }
    )
    evaluation = policy.evaluate(
        amount_cents=12000,
        category="meal",
        committed_cents=0,
    )
    assert evaluation.violations == [
        "category_limit_exceeded",
        "monthly_budget_exceeded",
    ]
    assert evaluation.requires_approval is True


def test_expense_policy_configuration_reaches_claim_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证报销策略配置达到报销单元数据对应的测试场景。

    Args:
        monkeypatch: pytest 提供的猴子补丁对象。
    """
    monkeypatch.setenv("AGENTFORGE_EXPENSE_CATEGORY_LIMITS", "meal=5000")
    monkeypatch.setenv("AGENTFORGE_EXPENSE_MONTHLY_BUDGET_CENTS", "10000")
    get_settings.cache_clear()
    try:
        client = TestClient(create_platform_app())
        response = client.post(
            "/v1/expense/claims",
            json={
                "tenant_id": "tenant-policy",
                "applicant_id": "employee-1",
                "amount_cents": 12000,
                "expense_date": "2026-10-19",
                "category": "meal",
                "idempotency_key": "policy-claim-1",
            },
        )
        assert response.status_code == 200
        policy = response.json()["metadata"]["policy"]
        assert policy["violations"] == [
            "category_limit_exceeded",
            "monthly_budget_exceeded",
        ]
        configured = client.get(
            "/v1/expense/policies",
            params={"tenant_id": "tenant-policy"},
        ).json()
        assert configured["category_limits"] == {"meal": 5000}
        assert configured["monthly_budget_cents"] == 10000
    finally:
        get_settings.cache_clear()
