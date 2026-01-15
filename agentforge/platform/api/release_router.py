"""AgentForge 平台 API 层：release_router。

本模块定义 release_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_release_router。
"""

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
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        container: Any，调用方传入的 container 参数。

    Returns:
        APIRouter，函数执行后的结果。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
    """
    router = APIRouter(prefix="/v1/release", tags=["release"])

    @router.post("/prompts")
    async def register_prompt(
        request: Request,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """执行 register_prompt 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。
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
        """执行 publish_prompt 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            name: str，调用方传入的 name 参数。
            version: str，调用方传入的 version 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。
        """
        registry: PromptRegistry = container.prompt_registry
        template = registry.publish(name, version)
        return template.model_dump(mode="json")

    @router.post("/models")
    async def register_model(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """执行 register_model 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。
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
        """执行 evaluate_gate 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
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
