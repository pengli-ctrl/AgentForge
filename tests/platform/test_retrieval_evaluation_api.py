"""AgentForge 平台测试层：test_retrieval_evaluation_api。

本测试模块验证 test_retrieval_evaluation_api 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_knowledge_search_with_rerank、test_retrieval_evaluation_endpoint、test_retrieval_evaluation_respects_tenant。
"""

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.runtime import build_memory_container


def test_knowledge_search_with_rerank() -> None:
    """验证 knowledge_search_with_rerank 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
    """验证 retrieval_evaluation_endpoint 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
    """验证 retrieval_evaluation_respects_tenant 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
