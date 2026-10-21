"""控制台路由模块。"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from agentforge.platform.application.ports import CostRepository
from agentforge.platform.domain.connector import spec_to_public_dict
from agentforge.platform.domain.cron import CronExpressionError, CronSchedule, is_cron_cadence
from agentforge.platform.domain.reporting import ReportFormat, ReportType
from agentforge.platform.domain.tenant_quota import TenantQuota


def create_console_router(
    quota_repository=None,
    cost_repository: CostRepository | None = None,
    outbox_store=None,
    audit_repository=None,
    ticket_repository=None,
    dashboard_service=None,
    connector_registry=None,
    connector_repository=None,
    authenticator=None,
    report_service=None,
) -> APIRouter:
    """创建控制台路由。

    Args:
        quota_repository: 配额仓储。
        cost_repository: 成本仓储。
        outbox_store: Outbox存储。
        audit_repository: 审计仓储。
        ticket_repository: 工单仓储。
        dashboard_service: 看板服务。
        connector_registry: 连接器注册表。
        connector_repository: 连接器仓储。
        authenticator: 认证器实例。
        report_service: 报告服务。

    Yields:
        逐次生成的结果。
    """
    router = APIRouter(prefix="/v1/console", tags=["console"])

    @router.get("/overview")
    async def overview(tenant_id: str) -> dict:
        """处理 GET /overview 请求，查询总览。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        result: dict = {"tenant_id": tenant_id}

        # 验证配额控制，确保预算和硬限额生效。
        quota: TenantQuota | None = None
        if quota_repository is not None:
            quota = await quota_repository.get(tenant_id)
        used = 0.0
        if cost_repository is not None:
            used = await cost_repository.total_for_tenant(tenant_id)
        if quota is not None:
            result["quota"] = quota.model_dump(mode="json")
            result["quota"]["configured"] = True
            result["quota"]["usage"] = quota.usage_status(used)
        else:
            result["quota"] = {"configured": False, "used": used}
        result["cost"] = {"used": used}

        if ticket_repository is not None:
            result["tasks"] = await _status_counts(ticket_repository, tenant_id)

        # 验证失败场景，确保异常路径能够被正确处理。
        if outbox_store is not None:
            failed = await outbox_store.list_failed(limit=50)
            result["dlq"] = {"failed_count": len(failed)}
        else:
            result["dlq"] = {"failed_count": 0}

        # 验证审计记录，确保关键行为可追踪。
        if audit_repository is not None:
            events = await audit_repository.list_events(tenant_id, limit=20)
            result["audit"] = {
                "recent_count": len(events),
                "recent": [
                    {
                        "event_id": e.event_id,
                        "action": e.action,
                        "resource_type": e.resource_type,
                        "resource_id": e.resource_id,
                        "occurred_at": e.occurred_at.isoformat(),
                    }
                    for e in events
                ],
            }
        else:
            result["audit"] = {"recent_count": 0, "recent": []}

        return result

    @router.get("/tickets")
    async def list_tickets(
        request: Request,
        tenant_id: str,
        status: str | None = None,
        assigned_team: str | None = None,
        assignee_id: str | None = None,
        queue: str | None = None,
        overdue: bool = False,
        due_before: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict:
        """处理 GET /tickets 请求，查询工单。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            status: 目标状态。
            assigned_team: 输入参数。
            assignee_id: 处理人 ID。
            queue: 队列。
            overdue: 逾期。
            due_before: 到期之前。
            limit: 返回记录的最大数量。
            cursor: 分页游标。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        if ticket_repository is None:
            raise HTTPException(status_code=503, detail="Ticket repository is not configured")
        tickets, next_cursor = await ticket_repository.list(
            tenant_id,
            status=status,
            limit=limit,
            cursor=cursor,
            assigned_team=assigned_team,
            assignee_id=assignee_id,
            queue=queue,
            overdue=overdue,
            due_before=due_before,
        )
        return {
            "tenant_id": tenant_id,
            "tickets": [_ticket_summary(t) for t in tickets],
            "next_cursor": next_cursor,
        }

    @router.get("/inbox")
    async def approval_inbox(
        request: Request, tenant_id: str, limit: int = 100, cursor: str | None = None
    ) -> dict:
        """处理 GET /inbox 请求，查询审批收件箱。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。
            cursor: 分页游标。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        if ticket_repository is None:
            raise HTTPException(status_code=503, detail="Ticket repository is not configured")
        tickets, next_cursor = await ticket_repository.list(
            tenant_id, status="waiting_approval", limit=limit, cursor=cursor
        )
        return {
            "tenant_id": tenant_id,
            "items": [_ticket_summary(t) for t in tickets],
            "next_cursor": next_cursor,
        }

    @router.get("/costs")
    async def costs_overview(request: Request) -> dict:
        """处理 GET /costs 请求，查询成本总览。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        if quota_repository is None or cost_repository is None:
            raise HTTPException(
                status_code=503, detail="Cost or quota repository is not configured"
            )
        tenants = await _list_tenant_ids(quota_repository, cost_repository)
        rows = []
        total = 0.0
        for tenant_id in tenants:
            used = await cost_repository.total_for_tenant(tenant_id)
            total += used
            quota = await quota_repository.get(tenant_id)
            row: dict = {"tenant_id": tenant_id, "used": used}
            if quota is not None:
                row["quota"] = quota.model_dump(mode="json")
                row["quota"]["configured"] = True
                row["quota"]["usage"] = quota.usage_status(used)
            else:
                row["quota"] = {"configured": False}
            rows.append(row)
        return {"tenants": rows, "total_cost": total}

    @router.get("/cost-trend")
    async def cost_trend(tenant_id: str, days: int = 30) -> dict:
        """处理 GET /cost-trend 请求，查询成本趋势。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            days: 统计天数。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        if dashboard_service is None:
            raise HTTPException(status_code=503, detail="Dashboard service is not configured")
        days = max(1, min(days, 365))
        return await dashboard_service.cost_trend(tenant_id, days=days)

    @router.get("/model-distribution")
    async def model_distribution(tenant_id: str) -> dict:
        """处理 GET /model-distribution 请求，查询模型分布。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        if dashboard_service is None:
            raise HTTPException(status_code=503, detail="Dashboard service is not configured")
        return await dashboard_service.model_distribution(tenant_id)

    @router.get("/quality")
    async def quality(tenant_id: str, limit: int = 10) -> dict:
        """处理 GET /quality 请求，查询质量。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        if dashboard_service is None:
            raise HTTPException(status_code=503, detail="Dashboard service is not configured")
        return await dashboard_service.quality_metrics(tenant_id, limit=limit)

    @router.get("/traces")
    async def traces(tenant_id: str | None = None, limit: int = 50) -> dict:
        """处理 GET /traces 请求，查询链路。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        if dashboard_service is None:
            raise HTTPException(status_code=503, detail="Dashboard service is not configured")
        return await dashboard_service.recent_traces(tenant_id=tenant_id, limit=limit)

    @router.get("/dashboard")
    async def dashboard(tenant_id: str) -> dict:
        """获取控制台看板数据。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        if dashboard_service is None:
            raise HTTPException(status_code=503, detail="Dashboard service is not configured")
        trend = await dashboard_service.cost_trend(tenant_id, days=30)
        distribution = await dashboard_service.model_distribution(tenant_id)
        quota = await dashboard_service.quota_snapshot(tenant_id)
        quality = await dashboard_service.quality_metrics(tenant_id)
        return {
            "tenant_id": tenant_id,
            "cost_trend": trend,
            "model_distribution": distribution,
            "quota": quota,
            "quality": quality,
        }

    @router.get("/tenants")
    async def list_tenants(request: Request) -> dict:
        """处理 GET /tenants 请求，查询租户。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if cost_repository is None:
            raise HTTPException(status_code=503, detail="Cost repository is not configured")
        tenant_ids = await _list_tenant_ids(quota_repository, cost_repository)
        rows = []
        for tenant_id in tenant_ids:
            row: dict = {"tenant_id": tenant_id}
            used = await cost_repository.total_for_tenant(tenant_id)
            row["used"] = used
            quota = None
            if quota_repository is not None:
                quota = await quota_repository.get(tenant_id)
            if quota is not None:
                row["quota"] = quota.model_dump(mode="json")
                row["quota"]["configured"] = True
                row["quota"]["usage"] = quota.usage_status(used)
                row["enabled"] = quota.enabled
            else:
                row["quota"] = {"configured": False}
                row["enabled"] = True
            rows.append(row)
        return {"tenants": rows}

    @router.get("/audit")
    async def list_audit(
        request: Request,
        tenant_id: str | None = None,
        limit: int = 100,
        action: str | None = None,
        actor_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
        cursor: str | None = None,
    ) -> dict:
        """处理 GET /audit 请求，查询审计。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。
            action: 待执行动作名称。
            actor_id: 执行操作的参与者 ID。
            resource_id: 资源 ID。
            resource_type: 资源类型。
            cursor: 分页游标。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if audit_repository is None:
            raise HTTPException(status_code=503, detail="Audit repository is not configured")
        events, next_cursor = await audit_repository.query_events(
            tenant_id=tenant_id,
            limit=limit,
            action=action,
            actor_id=actor_id,
            resource_id=resource_id,
            resource_type=resource_type,
            cursor=cursor,
        )
        return {
            "events": [event.model_dump(mode="json") for event in events],
            "next_cursor": next_cursor,
        }

    @router.get("/connectors")
    async def list_connectors(request: Request) -> dict:
        """处理 GET /connectors 请求，查询连接器。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if connector_repository is None:
            raise HTTPException(status_code=503, detail="Connector repository is not configured")
        specs = await connector_repository.list_specs(tenant_id=None)
        rows = []
        for spec in specs:
            row = spec_to_public_dict(spec)
            if connector_registry is not None:
                health = await connector_registry.health(spec.connector_id)
                row["health"] = health.model_dump(mode="json") if health is not None else None
            rows.append(row)
        return {"connectors": rows}

    @router.post("/connectors/{connector_id}/enabled")
    async def set_connector_enabled(
        request: Request,
        connector_id: str,
        body: dict,
    ) -> dict:
        """处理 POST /connectors/{connector_id}/enabled 请求，设置连接器启用。

        Args:
            request: 当前 HTTP 请求。
            connector_id: 连接器 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if connector_repository is None:
            raise HTTPException(status_code=503, detail="Connector repository is not configured")
        spec = await connector_repository.get_spec(connector_id)
        if spec is None:
            raise HTTPException(status_code=404, detail="connector not found")
        spec.enabled = bool(body.get("enabled", True))
        await connector_repository.save_spec(spec)
        return spec_to_public_dict(spec)

    @router.get("/reports/export")
    async def export_report(
        request: Request,
        report_type: str = "cost",
        tenant_id: str = "default",
        format: str = "json",
        days: int = 30,
    ) -> Response:
        """处理 GET /reports/export 请求，导出报告。

        Args:
            request: 当前 HTTP 请求。
            report_type: 报告类型。
            tenant_id: 租户 ID，用于数据隔离。
            format: 格式化。
            days: 统计天数。

        Returns:
            响应结果。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        try:
            rtype = ReportType(report_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid report_type")
        fmt = ReportFormat(format)
        report = await report_service.generate(
            report_type=rtype, tenant_id=tenant_id, fmt=fmt, days=days
        )
        if fmt == ReportFormat.CSV:
            payload = report.to_csv()
            headers = {"Content-Disposition": f'attachment; filename="report_{rtype.value}.csv"'}
            return Response(content=payload, media_type="text/csv", headers=headers)
        return Response(
            content=report.to_json(),
            media_type="application/json",
        )

    @router.post("/reports/schedule")
    async def create_schedule(request: Request, body: dict) -> dict:
        """处理 POST /reports/schedule 请求，创建调度。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        try:
            rtype = ReportType(body.get("report_type", "cost"))
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid report_type")
        tenant_id = str(body.get("tenant_id", "default"))
        cadence = str(body.get("cadence", "daily"))
        if is_cron_cadence(cadence):
            try:
                CronSchedule(cadence)
            except CronExpressionError:
                raise HTTPException(status_code=400, detail="invalid cadence cron expression")
        elif cadence not in ("daily", "weekly", "monthly"):
            raise HTTPException(status_code=400, detail="invalid cadence")
        retention_days = body.get("retention_days")
        if retention_days is not None:
            try:
                retention_days = int(retention_days)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="invalid retention_days")
        schedule = await report_service.schedule(
            tenant_id=tenant_id,
            report_type=rtype,
            cadence=cadence,
            retention_days=retention_days,
        )
        return schedule.model_dump(mode="json")

    @router.get("/reports/schedules")
    async def list_schedules(request: Request, tenant_id: str | None = None) -> dict:
        """处理 GET /reports/schedules 请求，查询调度。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        schedules = await report_service.list_schedules(tenant_id=tenant_id)
        return {"schedules": schedules}

    @router.delete("/reports/schedule/{report_id}")
    async def delete_schedule(request: Request, report_id: str) -> dict:
        """处理 DELETE /reports/schedule/{report_id} 请求，删除调度。

        Args:
            request: 当前 HTTP 请求。
            report_id: 报告 ID。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        await report_service.delete_schedule(report_id)
        return {"deleted": report_id}

    @router.post("/reports/schedule/{report_id}/enabled")
    async def set_schedule_enabled(request: Request, report_id: str, body: dict) -> dict:
        """处理 POST /reports/schedule/{report_id}/enabled 请求，设置调度启用。

        Args:
            request: 当前 HTTP 请求。
            report_id: 报告 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        enabled = bool(body.get("enabled", True))
        try:
            sched = await report_service.set_schedule_enabled(report_id, enabled)
        except KeyError:
            raise HTTPException(status_code=404, detail="schedule not found")
        return sched.model_dump(mode="json")

    @router.post("/reports/run-due")
    async def run_due(request: Request, body: dict = {}) -> dict:
        """处理 POST /reports/run-due 请求，运行到期。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        default_retention_days = body.get("default_retention_days")
        if default_retention_days is not None:
            try:
                default_retention_days = int(default_retention_days)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="invalid default_retention_days")
        return await report_service.run_due(default_retention_days=default_retention_days)

    @router.get("/reports/runs")
    async def list_runs(
        request: Request,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
        archived: bool | None = None,
        cursor: str | None = None,
    ) -> dict:
        """处理 GET /reports/runs 请求，查询运行记录。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            report_type: 报告类型。
            limit: 返回记录的最大数量。
            archived: 已归档。
            cursor: 分页游标。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        runs, next_cursor = await report_service.list_runs_paginated(
            tenant_id=tenant_id,
            report_type=report_type,
            limit=limit,
            archived=archived,
            cursor=cursor,
        )
        return {"runs": runs, "next_cursor": next_cursor}

    @router.post("/reports/runs/{run_id}/archive")
    async def archive_run(request: Request, run_id: str, body: dict) -> dict:
        """处理 POST /reports/runs/{run_id}/archive 请求，提交归档运行。

        Args:
            request: 当前 HTTP 请求。
            run_id: 运行记录 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        archived = bool(body.get("archived", True))
        try:
            return await report_service.archive_run(run_id, archived=archived)
        except KeyError:
            raise HTTPException(status_code=404, detail="report run not found")

    @router.get("/reports/runs/archive")
    async def export_archive(
        request: Request,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> Response:
        """处理 GET /reports/runs/archive 请求，导出归档。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Yields:
            逐次生成的结果。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        fd, path = tempfile.mkstemp(suffix=".zip")
        with os.fdopen(fd, "wb") as sink:
            await report_service.export_archive_to(sink, tenant_id=tenant_id, limit=limit)
        headers = {"Content-Disposition": 'attachment; filename="report_runs_archive.zip"'}

        def _iter_zip() -> Iterator[bytes]:
            """逐项读取 ZIP 归档内容。

            Yields:
                逐次生成的结果。
            """
            try:
                with open(path, "rb") as f:
                    while chunk := f.read(64 * 1024):
                        yield chunk
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass

        return StreamingResponse(_iter_zip(), media_type="application/zip", headers=headers)

    @router.get("/reports/runs/{run_id}")
    async def get_run(
        request: Request,
        run_id: str,
        format: str = "json",
    ) -> Response:
        """处理 GET /reports/runs/{run_id} 请求，获取运行。

        Args:
            request: 当前 HTTP 请求。
            run_id: 运行记录 ID。
            format: 格式化。

        Returns:
            响应结果。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        run = await report_service.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="report run not found")
        fmt = ReportFormat(format)
        if fmt == ReportFormat.CSV:
            headers = {"Content-Disposition": f'attachment; filename="run_{run_id}.csv"'}
            return Response(content=run.to_csv(), media_type="text/csv", headers=headers)
        return Response(content=run.to_json(), media_type="application/json")

    @router.post("/reports/runs/prune")
    async def prune_runs(request: Request, body: dict) -> dict:
        """处理 POST /reports/runs/prune 请求，清理运行记录。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        _authorize_admin(authenticator, request)
        if report_service is None:
            raise HTTPException(status_code=503, detail="Report service is not configured")
        retention_days = int(body.get("retention_days", 30))
        tenant_id = body.get("tenant_id")
        include_archived = bool(body.get("include_archived", False))
        return await report_service.prune_runs(
            retention_days=retention_days,
            tenant_id=tenant_id,
            include_archived=include_archived,
        )

    return router


def _authorize_admin(authenticator, request: Request) -> None:
    """授权管理。

    Args:
        authenticator: 认证器实例。
        request: 当前 HTTP 请求。
    """
    if authenticator is not None:
        authenticator.authorize_admin(request)


async def _status_counts(ticket_repository, tenant_id: str) -> dict:
    """处理状态。

    Args:
        ticket_repository: 工单仓储。
        tenant_id: 租户 ID，用于数据隔离。

    Returns:
        结构化结果字典。
    """
    counts: dict[str, int] = {}
    for status in (
        "new",
        "classifying",
        "waiting_review",
        "waiting_approval",
        "ready_to_publish",
        "published",
        "escalated",
        "failed",
        "cancelled",
    ):
        tickets, _ = await ticket_repository.list(tenant_id, status=status, limit=1000)
        counts[status] = len(tickets)
    return counts


async def _list_tenant_ids(quota_repository, cost_repository) -> list[str]:
    """查询租户。

    Args:
        quota_repository: 配额仓储。
        cost_repository: 成本仓储。

    Returns:
        结果列表。
    """
    ids: dict[str, None] = {}
    if hasattr(cost_repository, "list_tenants"):
        try:
            for tid in await cost_repository.list_tenants():
                ids.setdefault(tid, None)
        except Exception:
            pass
    try:
        for quota in await quota_repository.list():
            ids.setdefault(quota.tenant_id, None)
    except Exception:
        pass
    return list(ids.keys())


def _ticket_summary(t) -> dict:
    """执行工单摘要。

    Args:
        t: 输入参数。

    Returns:
        结构化结果字典。
    """
    return {
        "ticket_id": t.ticket_id,
        "status": t.status,
        "priority": t.priority,
        "subject": t.subject,
        "intent": t.intent,
        "product": t.product,
        "assigned_team": t.assigned_team,
        "assignee_id": t.assignee_id,
        "queue": t.metadata.get("queue"),
        "sla": t.metadata.get("sla"),
        "risk_level": t.risk_level,
        "confidence": t.confidence,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    }
