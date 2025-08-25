from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.runtime import build_memory_container


def test_knowledge_ingest_and_search() -> None:
    client = TestClient(create_platform_app(build_memory_container()))
    response = client.post(
        "/v1/knowledge/documents",
        json={
            "tenant_id": "tenant-1",
            "title": "Refund policy",
            "content": "Refunds are available within seven days for product issues.",
        },
    )
    assert response.status_code == 200
    search = client.get(
        "/v1/knowledge/search",
        params={"tenant_id": "tenant-1", "query": "refund"},
    )
    assert search.status_code == 200
    payload = search.json()
    assert payload["mode"] == "hybrid"
    results = payload["results"]
    assert len(results) == 1
    assert results[0]["title"] == "Refund policy"


def test_knowledge_search_modes_and_weights() -> None:
    client = TestClient(create_platform_app(build_memory_container()))
    client.post(
        "/v1/knowledge/documents",
        json={
            "tenant_id": "tenant-1",
            "title": "Refund policy",
            "content": "Refunds are available within seven days for product issues.",
        },
    )
    for mode in ("hybrid", "keyword", "vector"):
        response = client.get(
            "/v1/knowledge/search",
            params={
                "tenant_id": "tenant-1",
                "query": "refund",
                "mode": mode,
                "fts_weight": 0.6,
                "vector_weight": 0.4,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == mode
        assert len(payload["results"]) == 1
        assert payload["results"][0]["title"] == "Refund policy"


def test_knowledge_search_respects_tenant_isolation() -> None:
    client = TestClient(create_platform_app(build_memory_container()))
    client.post(
        "/v1/knowledge/documents",
        json={
            "tenant_id": "tenant-1",
            "title": "Refund policy",
            "content": "Refunds are available within seven days.",
        },
    )
    client.post(
        "/v1/knowledge/documents",
        json={
            "tenant_id": "tenant-2",
            "title": "Refund secrets",
            "content": "Tenant two private refund manual.",
        },
    )
    # tenant-1 不能检索到 tenant-2 的私有文档
    search = client.get(
        "/v1/knowledge/search",
        params={"tenant_id": "tenant-1", "query": "refund"},
    )
    results = search.json()["results"]
    assert len(results) == 1
    assert results[0]["tenant_id"] == "tenant-1"
