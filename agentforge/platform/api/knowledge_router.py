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
    router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])

    @router.post("/documents")
    async def ingest_document(request: Request, body: dict[str, Any]) -> dict[str, Any]:
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
