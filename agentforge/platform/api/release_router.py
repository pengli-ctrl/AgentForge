from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.application.prompt_registry import PromptRegistry
from agentforge.platform.application.quality_gate_service import QualityGateService
from agentforge.platform.application.version_registry import ModelVersionRegistry
from agentforge.platform.domain.quality import (
    ClassificationGoldenItem,
    ModelVersion,
    PromptStatus,
    PromptTemplate,
    ReleaseCandidate,
)
from agentforge.platform.domain.retrieval import GoldenQuery


def create_release_router(container) -> APIRouter:
    router = APIRouter(prefix="/v1/release", tags=["release"])

    @router.post("/prompts")
    async def register_prompt(
        request: Request,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """注册一个 Prompt 模板版本。body 需含 name/version/content，可含 status。"""
        template = PromptTemplate(
            name=str(body["name"]),
            version=str(body["version"]),
            content=str(body["content"]),
            status=PromptStatus(str(body.get("status", "draft"))),
        )
        registry: PromptRegistry = container.prompt_registry
        saved = registry.register(template)
        return saved.model_dump(mode="json")

    @router.post("/prompts/{name}/{version}/publish")
    async def publish_prompt(
        request: Request,
        name: str,
        version: str,
    ) -> dict[str, Any]:
        """激活指定 Prompt 版本；同名其它版本自动降级为 DEPRECATED。"""
        registry: PromptRegistry = container.prompt_registry
        template = registry.publish(name, version)
        return template.model_dump(mode="json")

    @router.post("/models")
    async def register_model(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """注册一个模型版本。body 需含 name/provider/model_id/version。"""
        model = ModelVersion(
            name=str(body["name"]),
            provider=str(body["provider"]),
            model_id=str(body["model_id"]),
            version=str(body["version"]),
            capability_score=float(body.get("capability_score", 0.0)),
        )
        registry: ModelVersionRegistry = container.model_version_registry
        saved = registry.register(model)
        return saved.model_dump(mode="json")

    @router.post("/gate")
    async def evaluate_gate(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """对一条发布候选执行质量门禁。

        body 需含 candidate(ReleaseCandidate dict)，可选 retrieval(golden 查询列表 +
        options) 与 classification(分类 golden 列表)。返回 PASS/HOLD/BLOCK。
        """
        service: QualityGateService = container.quality_gate_service
        candidate_data = body.get("candidate")
        if not isinstance(candidate_data, dict) or not candidate_data:
            raise HTTPException(status_code=400, detail="candidate is required")
        candidate = ReleaseCandidate(**candidate_data)

        retrieval_report = None
        retrieval_body = body.get("retrieval")
        if isinstance(retrieval_body, dict):
            if container.retrieval_evaluation_service is None:
                raise HTTPException(
                    status_code=503, detail="Retrieval evaluation service is not configured"
                )
            golden_queries = [
                GoldenQuery(
                    tenant_id=str(item["tenant_id"]),
                    query=str(item["query"]),
                    expected_chunk_ids=list(item.get("expected_chunk_ids", [])),
                    expected_citations=list(item.get("expected_citations", [])),
                )
                for item in retrieval_body.get("queries", [])
            ]
            if not golden_queries:
                raise HTTPException(status_code=400, detail="retrieval.queries is empty")
            retrieval_report = await container.retrieval_evaluation_service.evaluate(
                golden_queries,
                k=int(retrieval_body.get("k", 5)),
                rerank=bool(retrieval_body.get("rerank", True)),
            )

        classification_report = None
        classification_body = body.get("classification")
        if isinstance(classification_body, dict):
            if container.classification_evaluation_service is None:
                raise HTTPException(
                    status_code=503,
                    detail="Classification evaluation service is not configured",
                )
            samples = [
                ClassificationGoldenItem(
                    tenant_id=str(item["tenant_id"]),
                    query=str(item["query"]),
                    expected_intent=str(item["expected_intent"]),
                    expected_priority=str(item["expected_priority"]),
                    expected_risk_level=str(item.get("expected_risk_level", "low")),
                    expect_structured=bool(item.get("expect_structured", True)),
                )
                for item in classification_body.get("samples", [])
            ]
            if not samples:
                raise HTTPException(status_code=400, detail="classification.samples is empty")
            classification_report = await container.classification_evaluation_service.evaluate(
                samples
            )

        result = service.gate(
            candidate,
            retrieval=retrieval_report,
            classification=classification_report,
        )
        return result.model_dump(mode="json")

    return router
