from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

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
        limit: int = 5,
    ) -> dict[str, Any]:
        container.authenticator.authorize_tenant(request, tenant_id)
        results = await container.knowledge_service.search(tenant_id, query, limit)
        return {"results": [result.model_dump(mode="json") for result in results]}

    return router
