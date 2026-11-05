"""测试本地集成资产。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_local_integration_assets_exist():
    """验证本地集成配置存在。"""
    assert (ROOT / "deploy/local/docker-compose.integration.yml").exists()
    assert (ROOT / "deploy/local/kind-envoy.yaml").exists()
    assert (ROOT / "deploy/local/litellm/config.yaml").exists()
    assert (ROOT / "deploy/local/mock_openai/app.py").exists()
