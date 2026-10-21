"""测试报销RAG回答测试模块。"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.domain.model import ModelRequest, ModelResponse
from agentforge.platform.domain.rbac import Role, RoleAssignment
from agentforge.platform.runtime import build_memory_container


class CitedModelGateway:
    """引用模型网关抽象。"""

    def __init__(self, *, invalid_citation: bool = False, fail: bool = False) -> None:
        """初始化引用模型。

        Args:
            invalid_citation: 无效引用。
            fail: 失败。
        """
        self.invalid_citation = invalid_citation
        self.fail = fail
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """完成引用模型。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            模型响应结果。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        self.requests.append(request)
        if self.fail:
            raise RuntimeError("model unavailable")
        allowed = list(request.metadata.get("allowed_citations", []))
        citations = ["outside-source"] if self.invalid_citation else allowed[:1]
        return ModelResponse(
            content="The approved record documents a client visit [source].",
            model="fake-grounded",
            provider="test",
            citations=citations,
        )


def _approve_claim(client: TestClient, tenant_id: str = "tenant-rag") -> dict:
    """批准报销单。

    Args:
        client: 客户端实例。
        tenant_id: 租户 ID，用于数据隔离。

    Returns:
        结构化结果字典。
    """
    created = client.post(
        "/v1/expense/claims",
        json={
            "tenant_id": tenant_id,
            "applicant_id": "employee-rag",
            "amount_cents": 8800,
            "expense_date": "2026-10-18",
            "category": "travel",
            "description": "Client visit",
            "idempotency_key": f"rag-{tenant_id}",
        },
    )
    assert created.status_code == 200, created.text
    claim = created.json()
    submitted = client.post(
        f"/v1/expense/claims/{claim['claim_id']}/submit",
        json={"tenant_id": tenant_id},
    )
    assert submitted.status_code == 200, submitted.text
    approved = client.post(
        f"/v1/expense/claims/{claim['claim_id']}/decision",
        json={
            "tenant_id": tenant_id,
            "decided_by": "approver-rag",
            "decision": "approve",
            "reason": "receipt verified",
        },
    )
    assert approved.status_code == 200, approved.text
    return approved.json()


def _container_with_approver(gateway: CitedModelGateway):
    """处理容器使用审批人。

    Args:
        gateway: 网关。

    Returns:
        处理结果。
    """
    container = build_memory_container(model_gateway=gateway)
    asyncio.run(
        container.rbac_repository.save_role(
            Role(
                role_id="rag-approver",
                tenant_id="tenant-rag",
                name="rag_approver",
                permissions=["expense.claim.approve"],
            )
        )
    )
    asyncio.run(
        container.rbac_repository.save_assignment(
            RoleAssignment(
                assignment_id="rag-assignment",
                tenant_id="tenant-rag",
                user_id="approver-rag",
                role_id="rag-approver",
            )
        )
    )
    return container


def test_answer_without_sources_fails_closed() -> None:
    """验证回答不包含来源失败已关闭对应的测试场景。"""
    gateway = CitedModelGateway()
    client = TestClient(create_platform_app(build_memory_container(model_gateway=gateway)))

    response = client.post(
        "/v1/expense/answer",
        json={"tenant_id": "tenant-empty", "question": "What travel claims exist?"},
    )

    assert response.status_code == 200
    assert response.json()["answered"] is False
    assert response.json()["reason"] == "no_sources"
    assert response.json()["citations"] == []
    assert response.json()["requires_human_review"] is True
    assert gateway.requests == []


def test_answer_returns_claim_and_attachment_citations() -> None:
    """验证回答返回报销单及附件引用对应的测试场景。"""
    gateway = CitedModelGateway()
    client = TestClient(create_platform_app(_container_with_approver(gateway)))
    claim = _approve_claim(client)

    response = client.post(
        "/v1/expense/answer",
        json={"tenant_id": "tenant-rag", "question": "Which records mention a client visit?"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answered"] is True
    assert body["reason"] == ""
    assert body["requires_human_review"] is True
    assert body["citations"][0]["claim_id"] == claim["claim_id"]
    assert body["citations"][0]["attachment_id"] is None
    assert body["citations"][0]["source_uri"] == f"expense://claims/{claim['claim_id']}"
    assert body["citations"][0]["excerpt"]
    assert gateway.requests[0].metadata["allowed_citations"] == [body["citations"][0]["chunk_id"]]


def test_answer_rejects_citations_outside_retrieved_sources() -> None:
    """验证回答拒绝引用已检索来源对应的测试场景。"""
    gateway = CitedModelGateway(invalid_citation=True)
    client = TestClient(create_platform_app(_container_with_approver(gateway)))
    _approve_claim(client)

    response = client.post(
        "/v1/expense/answer",
        json={"tenant_id": "tenant-rag", "question": "Which records mention a client visit?"},
    )

    assert response.status_code == 200
    assert response.json()["answered"] is False
    assert response.json()["reason"] == "unverifiable_answer"
    assert response.json()["citations"] == []


def test_answer_does_not_retrieve_another_tenants_claims() -> None:
    """验证回答会不检索另一个租户报销单对应的测试场景。"""
    gateway = CitedModelGateway()
    client = TestClient(create_platform_app(_container_with_approver(gateway)))
    _approve_claim(client)

    response = client.post(
        "/v1/expense/answer",
        json={"tenant_id": "tenant-other", "question": "Which records mention a client visit?"},
    )

    assert response.status_code == 200
    assert response.json()["answered"] is False
    assert response.json()["reason"] == "no_sources"
    assert response.json()["citations"] == []
    assert gateway.requests == []


def test_answer_degrades_safely_when_model_fails() -> None:
    """验证回答当模型失败对应的测试场景。"""
    gateway = CitedModelGateway(fail=True)
    client = TestClient(create_platform_app(_container_with_approver(gateway)))
    _approve_claim(client)

    response = client.post(
        "/v1/expense/answer",
        json={"tenant_id": "tenant-rag", "question": "Which records mention a client visit?"},
    )

    assert response.status_code == 200
    assert response.json()["answered"] is False
    assert response.json()["reason"] == "generation_failed"
    assert response.json()["requires_human_review"] is True
