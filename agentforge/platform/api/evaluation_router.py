"""评估路由模块。"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from agentforge.platform.domain.quality import ClassificationGoldenItem
from agentforge.platform.domain.retrieval import GoldenQuery
from agentforge.platform.runtime import ServiceContainer


def create_evaluation_router(container: ServiceContainer) -> APIRouter:
    """创建评估路由。

    Args:
        container: 服务容器。

    Returns:
        处理结果对象。
    """
    router = APIRouter(prefix="/v1/evaluations", tags=["evaluations"])

    @router.get("/summary")
    async def summary(request: Request, tenant_id: str) -> dict:
        """汇总信息。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        container.authenticator.authorize_tenant(request, tenant_id)
        if container.evaluation_repository is None:
            raise HTTPException(status_code=503, detail="Evaluation repository is not configured")
        return await container.evaluation_repository.summary(tenant_id)

    @router.get("/samples")
    async def list_samples(
        request: Request,
        tenant_id: str,
        limit: int = 100,
        action: str | None = None,
    ) -> dict:
        """处理 GET /samples 请求，查询样本。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。
            action: 待执行动作名称。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        container.authenticator.authorize_tenant(request, tenant_id)
        if container.evaluation_repository is None:
            raise HTTPException(status_code=503, detail="Evaluation repository is not configured")
        samples = await container.evaluation_repository.list_samples(
            tenant_id=tenant_id,
            limit=limit,
            action=action,
        )
        return {"samples": [sample.model_dump(mode="json") for sample in samples]}

    @router.post("/retrieval")
    async def retrieval_evaluation(
        request: Request,
        body: list[dict[str, Any]],
        tenant_id: str,
        k: int = Query(default=5),
        rerank: bool = Query(default=True),
        mode: Literal["hybrid", "keyword", "vector"] = Query(default="hybrid"),
    ) -> dict[str, Any]:
        """处理 POST /retrieval 请求，提交检索评估。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。
            tenant_id: 租户 ID，用于数据隔离。
            k: 返回结果数量上限。
            rerank: 重排。
            mode: 运行模式。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        if container.retrieval_evaluation_service is None:
            raise HTTPException(
                status_code=503, detail="Retrieval evaluation service is not configured"
            )
        container.authenticator.authorize_tenant(request, tenant_id)
        golden_queries = [
            GoldenQuery(
                tenant_id=item["tenant_id"],
                query=item["query"],
                expected_chunk_ids=item.get("expected_chunk_ids", []),
                expected_citations=item.get("expected_citations", []),
            )
            for item in body
        ]
        report = await container.retrieval_evaluation_service.evaluate(
            golden_queries,
            k=k,
            rerank=rerank,
            mode=mode,
        )
        return report.model_dump(mode="json")

    @router.post("/classification")
    async def classification_evaluation(
        request: Request,
        body: list[dict[str, Any]],
        tenant_id: str,
    ) -> dict[str, Any]:
        """处理 POST /classification 请求，提交分类评估。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        if container.classification_evaluation_service is None:
            raise HTTPException(
                status_code=503,
                detail="Classification evaluation service is not configured",
            )
        container.authenticator.authorize_tenant(request, tenant_id)
        samples = [
            ClassificationGoldenItem(
                tenant_id=item["tenant_id"],
                query=item["query"],
                expected_intent=item["expected_intent"],
                expected_priority=item["expected_priority"],
                expected_risk_level=item.get("expected_risk_level", "low"),
                expect_structured=item.get("expect_structured", True),
            )
            for item in body
        ]
        report = await container.classification_evaluation_service.evaluate(samples)
        return report.model_dump(mode="json")

    return router
