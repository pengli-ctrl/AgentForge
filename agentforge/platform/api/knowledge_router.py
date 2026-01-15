"""AgentForge 平台 API 层：knowledge_router。

本模块定义 knowledge_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_knowledge_router。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from agentforge.platform.domain.knowledge import (
    DEFAULT_FTS_WEIGHT,
    DEFAULT_VECTOR_WEIGHT,
    SearchMode,
)
from agentforge.platform.runtime import ServiceContainer


def create_knowledge_router(container: ServiceContainer) -> APIRouter:
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        container: ServiceContainer，调用方传入的 container 参数。

    Returns:
        APIRouter，函数执行后的结果。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
    """
    router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])

    @router.post("/documents")
    async def ingest_document(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """执行 ingest_document 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        title = body.get("title")
        content = body.get("content")
        if not all(isinstance(value, str) and value for value in (tenant_id, title, content)):
            raise HTTPException(status_code=422, detail="tenant_id, title and content are required")
        container.authenticator.authorize_tenant(request, tenant_id)
        document = await container.knowledge_service.ingest_document(
            tenant_id=tenant_id,
            title=title,
            content=content,
            source_uri=body.get("source_uri", ""),
        )
        return document.model_dump(mode="json")

    @router.get("/search")
    async def search(
        request: Request,
        tenant_id: str,
        query: str,
        limit: int = Query(default=5),
        mode: SearchMode = Query(default="hybrid"),
        fts_weight: float = Query(default=DEFAULT_FTS_WEIGHT),
        vector_weight: float = Query(default=DEFAULT_VECTOR_WEIGHT),
        rerank: bool = Query(default=False),
    ) -> dict[str, Any]:
        """执行 search 对应的核心操作，并保持调用契约稳定。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。
            query: str，调用方传入的 query 参数。
            limit: int，调用方传入的 limit 参数。
            mode: SearchMode，调用方传入的 mode 参数。
            fts_weight: float，调用方传入的 fts_weight 参数。
            vector_weight: float，调用方传入的 vector_weight 参数。
            rerank: bool，调用方传入的 rerank 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。
        """
        container.authenticator.authorize_tenant(request, tenant_id)
        results = await container.knowledge_service.search(
            tenant_id,
            query,
            limit,
            mode=mode,
            fts_weight=fts_weight,
            vector_weight=vector_weight,
            rerank=rerank,
        )
        return {
            "mode": mode,
            "limit": limit,
            "rerank": rerank,
            "results": [result.model_dump(mode="json") for result in results],
        }

    return router
