"""AgentForge 平台 API 层：evaluation_router。

本模块定义 evaluation_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_evaluation_router。
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from agentforge.platform.domain.quality import ClassificationGoldenItem
from agentforge.platform.domain.retrieval import GoldenQuery
from agentforge.platform.runtime import ServiceContainer


def create_evaluation_router(container: ServiceContainer) -> APIRouter:
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        container: ServiceContainer，调用方传入的 container 参数。

    Returns:
        APIRouter，函数执行后的结果。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
    """
    router = APIRouter(prefix="/v1/evaluations", tags=["evaluations"])

    @router.get("/summary")
    async def summary(request: Request, tenant_id: str) -> dict:
        """执行 summary 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。
            action: str | None，调用方传入的 action 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
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
        """对一批 Ground-Truth 查询执行离线召回与引用质量评估。

        每个 golden 查询需提供 tenant_id / query / expected_chunk_ids /
        expected_citations。返回 Recall@K、Precision@K、MRR、引用正确率。
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
        """对一批 Golden 分类样本执行离线分类质量评估。

        每个样本需提供 tenant_id / query / expected_intent / expected_priority /
        expected_risk_level。返回分类准确率、优先级准确率、结构化输出合法率、
        高风险漏报率。
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
