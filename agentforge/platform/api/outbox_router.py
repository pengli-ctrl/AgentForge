"""Outbox路由模块。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.runtime import ServiceContainer


def create_outbox_router(container: ServiceContainer) -> APIRouter:
    """创建Outboxrouter。

    Args:
        container: 服务容器。

    Returns:
        处理结果对象。
    """
    router = APIRouter(prefix="/v1/outbox", tags=["outbox"])

    @router.get("/failed")
    async def list_failed(request: Request, limit: int = 100) -> dict:
        """处理 GET /failed 请求，查询失败。

        Args:
            request: 当前 HTTP 请求。
            limit: 返回记录的最大数量。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        container.authenticator.authorize_admin(request)
        if container.outbox_store is None:
            raise HTTPException(status_code=503, detail="Outbox store is not configured")
        events = await container.outbox_store.list_failed(limit=limit)
        return {"events": events}

    @router.get("/events/count")
    async def count_events(request: Request, tenant_id: str | None = None) -> dict:
        """处理 GET /events/count 请求，统计事件。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        container.authenticator.authorize_admin(request)
        if container.outbox_store is None:
            raise HTTPException(status_code=503, detail="Outbox store is not configured")
        return await container.outbox_store.count_events(tenant_id=tenant_id)

    @router.get("/events")
    async def list_events(
        request: Request,
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict:
        """处理 GET /events 请求，查询事件。

        Args:
            request: 当前 HTTP 请求。
            status: 目标状态。
            limit: 返回记录的最大数量。
            cursor: 分页游标。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        container.authenticator.authorize_admin(request)
        if container.outbox_store is None:
            raise HTTPException(status_code=503, detail="Outbox store is not configured")
        events, next_cursor = await container.outbox_store.list_events(
            status=status,
            limit=limit,
            cursor=cursor,
        )
        return {"events": events, "next_cursor": next_cursor}

    @router.get("/events/{event_id}")
    async def event_detail(request: Request, event_id: str) -> dict:
        """处理 GET /events/{event_id} 请求，查询事件详情。

        Args:
            request: 当前 HTTP 请求。
            event_id: 事件 ID。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        container.authenticator.authorize_admin(request)
        if container.outbox_store is None:
            raise HTTPException(status_code=503, detail="Outbox store is not configured")
        event = await container.outbox_store.get_event(None, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Outbox event not found")
        return {"event": event}

    @router.post("/{event_id}/replay")
    async def replay(request: Request, event_id: str) -> dict:
        """重放指定事件。

        Args:
            request: 当前 HTTP 请求。
            event_id: 事件 ID。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        container.authenticator.authorize_admin(request)
        if container.outbox_store is None:
            raise HTTPException(status_code=503, detail="Outbox store is not configured")
        if not await container.outbox_store.replay(event_id):
            raise HTTPException(status_code=404, detail="Outbox event not found")
        return {"replayed": True, "event_id": event_id}

    @router.post("/{event_id}/discard")
    async def discard(request: Request, event_id: str) -> dict:
        """处理 POST /{event_id}/discard 请求，提交丢弃。

        Args:
            request: 当前 HTTP 请求。
            event_id: 事件 ID。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        container.authenticator.authorize_admin(request)
        if container.outbox_store is None:
            raise HTTPException(status_code=503, detail="Outbox store is not configured")
        if not await container.outbox_store.discard(None, event_id):
            raise HTTPException(status_code=404, detail="Outbox event not found")
        return {"discarded": True, "event_id": event_id}

    @router.post("/replay-failed")
    async def replay_failed(request: Request, limit: int = 100) -> dict:
        """处理 POST /replay-failed 请求，重放失败。

        Args:
            request: 当前 HTTP 请求。
            limit: 返回记录的最大数量。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
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
