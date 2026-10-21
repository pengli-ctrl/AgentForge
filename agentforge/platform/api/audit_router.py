"""审计路由模块。"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.risk import RiskLevel
from agentforge.platform.runtime import ServiceContainer
from agentforge.platform.security.redaction import redact_sensitive


def create_audit_router(container: ServiceContainer) -> APIRouter:
    """创建审计路由。

    Args:
        container: 服务容器。

    Returns:
        处理结果对象。
    """
    router = APIRouter(prefix="/v1/audit", tags=["audit"])

    @router.get("")
    async def list_events(
        request: Request,
        tenant_id: str | None = None,
        limit: int = 100,
        resource_id: str | None = None,
        action: str | None = None,
        actor_id: str | None = None,
        resource_type: str | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """处理 GET 请求，查询事件。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。
            resource_id: 资源 ID。
            action: 待执行动作名称。
            actor_id: 执行操作的参与者 ID。
            resource_type: 资源类型。
            cursor: 分页游标。

        Returns:
            结构化结果字典。
        """
        _authorize_read(container, request, tenant_id)
        events, next_cursor = await _query(
            container,
            tenant_id=tenant_id,
            limit=limit,
            resource_id=resource_id,
            action=action,
            actor_id=actor_id,
            resource_type=resource_type,
            cursor=cursor,
        )
        return {
            "events": [event.model_dump(mode="json") for event in events],
            "next_cursor": next_cursor,
        }

    @router.get("/export")
    async def export_events(
        request: Request,
        tenant_id: str | None = None,
        format: str = "json",
        limit: int = 1000,
        redact: bool = True,
    ) -> Response:
        """处理 GET /export 请求，导出事件。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            format: 格式化。
            limit: 返回记录的最大数量。
            redact: 输入参数。

        Returns:
            响应结果。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_read(container, request, tenant_id)
        if format not in {"json", "csv"}:
            raise HTTPException(status_code=422, detail="format must be json or csv")
        if limit < 1 or limit > 10000:
            raise HTTPException(status_code=422, detail="limit must be between 1 and 10000")
        events, _ = await _query(container, tenant_id=tenant_id, limit=limit)
        rows = [_event_row(event, redact=redact) for event in events]
        if format == "json":
            import json

            return Response(
                content=json.dumps(rows, ensure_ascii=False),
                media_type="application/json",
                headers={"Content-Disposition": 'attachment; filename="audit-export.json"'},
            )
        buffer = io.StringIO()
        fieldnames = (
            list(rows[0])
            if rows
            else [
                "event_id",
                "tenant_id",
                "action",
                "resource_type",
                "resource_id",
                "risk_level",
                "actor_type",
                "actor_id",
                "trace_id",
                "occurred_at",
                "payload",
            ]
        )
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="audit-export.csv"'},
        )

    @router.post("/retention/purge")
    async def purge_events(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """处理 POST /retention/purge 请求，清除事件。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        container.authenticator.authorize_admin(request)
        tenant_id = body.get("tenant_id")
        actor_id = body.get("actor_id")
        confirmation = body.get("confirmation")
        before_raw = body.get("before")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise HTTPException(status_code=422, detail="tenant_id is required")
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise HTTPException(status_code=422, detail="actor_id is required")
        if confirmation != tenant_id:
            raise HTTPException(status_code=422, detail="confirmation must match tenant_id")
        if not isinstance(before_raw, str):
            raise HTTPException(status_code=422, detail="before must be an ISO timestamp")
        try:
            before = datetime.fromisoformat(before_raw)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid before timestamp") from exc
        if before.tzinfo is None:
            before = before.replace(tzinfo=timezone.utc)
        repository = container.audit_repository
        if repository is None or not hasattr(repository, "delete_events_before"):
            raise HTTPException(status_code=503, detail="Audit retention is not configured")
        deleted = await repository.delete_events_before(tenant_id, before)
        await repository.save(
            AuditEvent(
                event_id=f"audit-retention-{tenant_id}-{int(before.timestamp())}",
                tenant_id=tenant_id,
                action="audit.retention.purged",
                resource_type="audit",
                resource_id=tenant_id,
                risk_level=RiskLevel.HIGH,
                actor_type="user",
                actor_id=actor_id,
                payload={"deleted": deleted, "before": before.isoformat()},
            )
        )
        return {"tenant_id": tenant_id, "deleted": deleted, "before": before.isoformat()}

    return router


def _authorize_read(
    container: ServiceContainer,
    request: Request,
    tenant_id: str | None,
) -> None:
    """授权读取。

    Args:
        container: 服务容器。
        request: 当前 HTTP 请求。
        tenant_id: 租户 ID，用于数据隔离。
    """
    if tenant_id is None:
        container.authenticator.authorize_admin(request)
    else:
        container.authenticator.authorize_tenant(request, tenant_id)


async def _query(container: ServiceContainer, **kwargs: Any) -> tuple[list[AuditEvent], str | None]:
    """查询记录。

    Args:
        container: 服务容器。
        kwargs: 关键字参数。

    Returns:
        结果元组。

    Raises:
        HTTPException: 请求参数、状态或依赖不满足要求时抛出。
    """
    repository = container.audit_repository
    if repository is None:
        raise HTTPException(status_code=503, detail="Audit repository is not configured")
    return await repository.query_events(**kwargs)


def _event_row(event: AuditEvent, *, redact: bool) -> dict[str, Any]:
    """处理事件记录。

    Args:
        event: 待处理事件。
        redact: 输入参数。

    Returns:
        结构化结果字典。
    """
    row = event.model_dump(mode="json")
    return redact_sensitive(row) if redact else row


__all__ = ["create_audit_router"]
