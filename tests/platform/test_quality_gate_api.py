"""AgentForge 平台测试层：test_quality_gate_api。

本测试模块验证 test_quality_gate_api 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_registration_api_prompt_and_model、test_quality_gate_api_pass、test_quality_gate_api_block_on_recall、test_quality_gate_api_requires_candidate。
"""

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.api.security import ApiKeyAuthenticator
from agentforge.platform.domain.quality import ModelVersion, PromptTemplate
from agentforge.platform.runtime import build_memory_container


def _app() -> TestClient:
    """执行 _app 对应的逻辑，并返回处理结果。

    Returns:
        TestClient，函数执行后的结果。
    """
    container = build_memory_container(
        authenticator=ApiKeyAuthenticator(enabled=False),
    )
    # 预置 prompt 与模型版本，便于门禁接口复用
    container.prompt_registry.register(
        PromptTemplate(name="reply", version="1.0", content="Reply to {question}")
    )
    container.prompt_registry.publish("reply", "1.0")
    container.model_version_registry.register(
        ModelVersion(
            name="gpt",
            provider="litellm",
            model_id="gpt-4",
            version="1.0",
            capability_score=8.0,
        )
    )
    app = create_platform_app(container)
    return TestClient(app)


def test_registration_api_prompt_and_model() -> None:
    """验证 registration_api_prompt_and_model 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    client = _app()
    resp = client.post(
        "/v1/evaluations/classification?tenant_id=t1",
        json=[
            {
                "tenant_id": "t1",
                "query": "I want a refund",
                "expected_intent": "complaint_or_refund",
                "expected_priority": "p0",
                "expected_risk_level": "high",
            },
            {
                "tenant_id": "t1",
                "query": "What is the price?",
                "expected_intent": "sales_question",
                "expected_priority": "p2",
                "expected_risk_level": "low",
            },
        ],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_count"] == 2
    assert body["classification_accuracy"] == 1.0
    assert body["priority_accuracy"] == 1.0
    assert body["high_risk_miss_rate"] == 0.0


def test_quality_gate_api_pass() -> None:
    """验证 quality_gate_api_pass 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    client = _app()
    body = {
        "candidate": {
            "candidate_id": "c1",
            "tenant_id": "t1",
            "prompt_name": "reply",
            "prompt_version": "1.0",
            "model_name": "gpt",
            "model_version": "1.0",
        },
        "classification": {
            "samples": [
                {
                    "tenant_id": "t1",
                    "query": "I want a refund",
                    "expected_intent": "complaint_or_refund",
                    "expected_priority": "p0",
                    "expected_risk_level": "high",
                }
            ]
        },
    }
    resp = client.post("/v1/release/gate", json=body)
    assert resp.status_code == 200
    result = resp.json()
    assert result["verdict"] == "pass"


def test_quality_gate_api_block_on_recall() -> None:
    """验证 quality_gate_api_block_on_recall 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    client = _app()
    body = {
        "candidate": {
            "candidate_id": "c2",
            "tenant_id": "t1",
            "prompt_name": "reply",
            "prompt_version": "1.0",
            "model_name": "gpt",
            "model_version": "1.0",
        },
        "retrieval": {
            "queries": [
                {
                    "tenant_id": "t1",
                    "query": "refund within seven days",
                    "expected_chunk_ids": ["doc-x"],
                    "expected_citations": ["doc-x"],
                }
            ]
        },
    }
    resp = client.post("/v1/release/gate", json=body)
    assert resp.status_code == 200
    result = resp.json()
    # 没有种子数据时召回应失败 → BLOCK
    assert result["verdict"] == "block"


def test_quality_gate_api_requires_candidate() -> None:
    """验证 quality_gate_api_requires_candidate 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    client = _app()
    resp = client.post("/v1/release/gate", json={})
    assert resp.status_code == 400
