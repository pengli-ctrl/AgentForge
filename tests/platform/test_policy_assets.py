"""验证授权策略资产存在。"""

from pathlib import Path


def test_opa_policy_asset_exists() -> None:
    """验证 Rego 策略文件存在。"""
    policy = Path(__file__).resolve().parents[2] / "policies" / "agentforge.rego"
    assert policy.exists()
    assert "requires_approval" in policy.read_text(encoding="utf-8")