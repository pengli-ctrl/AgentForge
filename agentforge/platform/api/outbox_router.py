from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.runtime import ServiceContainer


def create_outbox_router(container: ServiceContainer) -> APIRouter:
    router = APIRouter(prefix="/v1/outbox", tags=["outbox"])

    @router.get("/failed")
    async def list_failed(request: Request, limit: int = 100) -> dict:
        container.authenticator.authorize_admin(request)
        if container.outbox_store is None:
            raise HTTPException(status_code=503, detail="Outbox store is not configured")
        events = await container.outbox_store.list_failed(limit=limit)
        return {"events": events}

    @router.post("/{event_id}/replay")
    async def replay(request: Request, event_id: str) -> dict:
        container.authenticator.authorize_admin(request)
        if container.outbox_store is None:
            raise HTTPException(status_code=503, detail="Outbox store is not configured")
        if not await container.outbox_store.replay(event_id):
            raise HTTPException(status_code=404, detail="Outbox event not found")
        return {"replayed": True, "event_id": event_id}

    @router.post("/replay-failed")
    async def replay_failed(request: Request, limit: int = 100) -> dict:
        container.authenticator.authorize_admin(request)
        if container.outbox_store is None:
            raise HTTPException(status_code=503, detail="Outbox store is not configured")
        events = await container.outbox_store.list_failed(limit=limit)
        replayed = 0
        for event in events:
            if await container.outbox_store.replay(event["event_id"]):
                replayed += 1
        return {"replayed": replayed}

    return router
