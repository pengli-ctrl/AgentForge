from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.domain.cost import CostRecord
from agentforge.platform.infrastructure.memory_cost_repository import MemoryCostRepository
from agentforge.platform.runtime import build_memory_container


def _client():
    container = build_memory_container()
    app = create_platform_app(container)
    return container, TestClient(app)


def test_quota_crud() -> None:
    container, client = _client()
    r = client.put(
        "/v1/quotas/t1",
        json={
            "monthly_limit": 100.0,
            "warning_threshold": 0.8,
            "hard_limit": 1.0,
            "enabled": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["monthly_limit"] == 100.0

    got = client.get("/v1/quotas/t1").json()
    assert got["configured"] is True
    assert got["usage"]["status"] in {"active", "warning", "blocked"}

    listed = client.get("/v1/quotas").json()
    assert [q["tenant_id"] for q in listed["quotas"]] == ["t1"]

    deleted = client.delete("/v1/quotas/t1").json()
    assert deleted["deleted"] == "t1"
    assert client.get("/v1/quotas/t1").json()["configured"] is False


def test_console_overview() -> None:
    container, client = _client()
    client.put(
        "/v1/quotas/t1",
        json={"monthly_limit": 100.0, "warning_threshold": 0.8, "hard_limit": 1.0, "enabled": True},
    )
    assert isinstance(container.cost_repository, MemoryCostRepository)
    container.cost_repository.records.append(
        CostRecord(
            tenant_id="t1",
            task_id="task-1",
            model_name="gpt-x",
            provider="openai",
            input_tokens=100,
            output_tokens=50,
            amount=12.5,
            created_at=datetime.now(timezone.utc),
        )
    )

    overview = client.get("/v1/console/overview", params={"tenant_id": "t1"}).json()
    assert overview["tenant_id"] == "t1"
    assert overview["quota"]["configured"] is True
    assert overview["cost"]["used"] == 12.5
    assert "dlq" in overview
    assert "audit" in overview
