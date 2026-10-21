"""知识路由模块。"""

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
    """创建知识路由。

    Args:
        container: 服务容器。

    Returns:
        处理结果对象。
    """
    router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])

    @router.post("/documents")
    async def ingest_document(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """处理 POST /documents 请求，写入文档。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
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
        """搜索与查询条件匹配的数据。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            query: 检索或筛选查询。
            limit: 返回记录的最大数量。
            mode: 运行模式。
            fts_weight: 输入参数。
            vector_weight: 输入参数。
            rerank: 重排。

        Returns:
            结构化结果字典。
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
