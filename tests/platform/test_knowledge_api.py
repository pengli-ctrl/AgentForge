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
    results = search.json()["results"]
    assert len(results) == 1
    assert results[0]["title"] == "Refund policy"
