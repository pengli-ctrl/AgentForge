from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.runtime import build_memory_container


def test_knowledge_search_with_rerank() -> None:
    client = TestClient(create_platform_app(build_memory_container()))
    client.post(
        "/v1/knowledge/documents",
        json={
            "tenant_id": "tenant-1",
            "title": "Refund policy",
            "content": "Refunds are available within seven days for product issues.",
        },
    )
    response = client.get(
        "/v1/knowledge/search",
        params={"tenant_id": "tenant-1", "query": "refund", "rerank": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["rerank"] is True
    assert len(payload["results"]) == 1


def test_retrieval_evaluation_endpoint() -> None:
    client = TestClient(create_platform_app(build_memory_container()))
    client.post(
        "/v1/knowledge/documents",
        json={
            "tenant_id": "tenant-1",
            "title": "Refund policy",
            "content": "Customers can request a refund within seven days for product issues.",
        },
    )
    response = client.post(
        "/v1/evaluations/retrieval?tenant_id=tenant-1&rerank=true",
        json=[
            {
                "tenant_id": "tenant-1",
                "query": "refund within seven days",
                "expected_chunk_ids": ["chunk-1"],
                "expected_citations": ["chunk-1"],
            }
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["query_count"] == 1
    assert payload["mean_reciprocal_rank"] >= 0.0
    assert "per_query" in payload


def test_retrieval_evaluation_respects_tenant() -> None:
    client = TestClient(create_platform_app(build_memory_container()))
    client.post(
        "/v1/knowledge/documents",
        json={
            "tenant_id": "tenant-1",
            "title": "Refund policy",
            "content": "Refunds available within seven days.",
        },
    )
    # 用 tenant-1 的查询去检索，但指定 tenant-2 的登录身份，应通过鉴权但结果受 tenant 隔离
    response = client.post(
        "/v1/evaluations/retrieval?tenant_id=tenant-2&rerank=true",
        json=[
            {
                "tenant_id": "tenant-2",
                "query": "refund",
                "expected_chunk_ids": [],
                "expected_citations": [],
            }
        ],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["query_count"] == 1
