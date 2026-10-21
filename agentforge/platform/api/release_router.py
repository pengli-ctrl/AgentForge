"""释放路由模块。"""

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
    """创建释放路由。

    Args:
        container: 服务容器。

    Returns:
        处理结果对象。
    """
    router = APIRouter(prefix="/v1/release", tags=["release"])

    @router.post("/prompts")
    async def register_prompt(
        request: Request,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /prompts 请求，注册提示词。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。
        """
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
        """处理 POST /prompts/{name}/{version}/publish 请求，发布提示词。

        Args:
            request: 当前 HTTP 请求。
            name: 资源或对象名称。
            version: 资源版本号。

        Returns:
            结构化结果字典。
        """
        registry: PromptRegistry = container.prompt_registry
        template = registry.publish(name, version)
        return template.model_dump(mode="json")

    @router.post("/models")
    async def register_model(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """处理 POST /models 请求，注册模型。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。
        """
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
        """处理 POST /gate 请求，评估门禁。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
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
