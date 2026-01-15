"""AgentForge 平台 API 层：outbox_router。

本模块定义 outbox_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_outbox_router。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.runtime import ServiceContainer


def create_outbox_router(container: ServiceContainer) -> APIRouter:
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        container: ServiceContainer，调用方传入的 container 参数。

    Returns:
        APIRouter，函数执行后的结果。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
    """
    router = APIRouter(prefix="/v1/outbox", tags=["outbox"])

    @router.get("/failed")
    async def list_failed(request: Request, limit: int = 100) -> dict:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        container.authenticator.authorize_admin(request)
        if container.outbox_store is None:
            raise HTTPException(status_code=503, detail="Outbox store is not configured")
        events = await container.outbox_store.list_failed(limit=limit)
        return {"events": events}

    @router.get("/events/count")
    async def count_events(request: Request, tenant_id: str | None = None) -> dict:
        """执行 count_events 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str | None，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
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
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            request: Request，调用方传入的 request 参数。
            status: str | None，调用方传入的 status 参数。
            limit: int，调用方传入的 limit 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
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
        """执行 event_detail 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            event_id: str，调用方传入的 event_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
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
        """执行 replay 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            event_id: str，调用方传入的 event_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        container.authenticator.authorize_admin(request)
        if container.outbox_store is None:
            raise HTTPException(status_code=503, detail="Outbox store is not configured")
        if not await container.outbox_store.replay(event_id):
            raise HTTPException(status_code=404, detail="Outbox event not found")
        return {"replayed": True, "event_id": event_id}

    @router.post("/{event_id}/discard")
    async def discard(request: Request, event_id: str) -> dict:
        """执行 discard 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            event_id: str，调用方传入的 event_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        container.authenticator.authorize_admin(request)
        if container.outbox_store is None:
            raise HTTPException(status_code=503, detail="Outbox store is not configured")
        if not await container.outbox_store.discard(None, event_id):
            raise HTTPException(status_code=404, detail="Outbox event not found")
        return {"discarded": True, "event_id": event_id}

    @router.post("/replay-failed")
    async def replay_failed(request: Request, limit: int = 100) -> dict:
        """执行 replay_failed 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
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
