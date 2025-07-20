from pathlib import Path

import yaml


def test_platform_compose_contains_api_worker_and_migration() -> None:
    path = Path("deploy/platform/docker-compose.platform.yml")
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = config["services"]
    assert "postgres" in services
    assert "temporal" in services
    assert "api" in services
    assert "worker" in services
    assert services["migrate"]["command"] == ["alembic", "upgrade", "head"]
    assert services["worker"]["command"] == ["python", "-m", "agentforge.platform.worker"]
