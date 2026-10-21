"""租户路由模块。"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from agentforge.platform.application.saas_plans import PlanCatalog
from agentforge.platform.application.tenant_lifecycle_service import (
    TenantLifecycleError,
    TenantLifecycleService,
)
from agentforge.platform.application.usage_metering_service import UsageMeteringService
from agentforge.platform.domain.tenant_account import TenantStatus
from agentforge.platform.domain.usage import UsageMetric


def create_tenant_control_router(
    lifecycle: TenantLifecycleService,
    usage: UsageMeteringService,
    plans: PlanCatalog,
    *,
    authenticator,
    outbox_store=None,
) -> APIRouter:
    """创建租户路由。

    Args:
        lifecycle: 生命周期。
        usage: 用量统计数据。
        plans: 套餐。
        authenticator: 认证器实例。
        outbox_store: Outbox存储。

    Returns:
        处理结果对象。
    """
    router = APIRouter(prefix="/v1/admin", tags=["tenant-control"])

    @router.get("/plans")
    async def list_plans(request: Request) -> dict[str, Any]:
        """处理 GET /plans 请求，查询套餐。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            结构化结果字典。
        """
        authenticator.authorize_admin(request)
        return {"plans": plans.public()}

    @router.get("/tenants")
    async def list_tenants(request: Request, limit: int = 100) -> dict[str, Any]:
        """处理 GET /tenants 请求，查询租户。

        Args:
            request: 当前 HTTP 请求。
            limit: 返回记录的最大数量。

        Returns:
            结构化结果字典。
        """
        authenticator.authorize_admin(request)
        accounts = await lifecycle.list(limit=max(1, min(limit, 500)))
        return {"tenants": [account.model_dump(mode="json") for account in accounts]}

    @router.post("/tenants")
    async def provision_tenant(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """处理 POST /tenants 请求，开通租户。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        authenticator.authorize_admin(request)
        required = {key: body.get(key) for key in ("tenant_id", "name", "plan_name", "actor_id")}
        if not all(isinstance(value, str) and value.strip() for value in required.values()):
            raise HTTPException(
                status_code=422,
                detail="tenant_id, name, plan_name and actor_id are required",
            )
        try:
            account = await lifecycle.provision(
                tenant_id=str(required["tenant_id"]),
                name=str(required["name"]),
                plan_name=str(required["plan_name"]),
                actor_id=str(required["actor_id"]),
            )
        except TenantLifecycleError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _account_payload(account, plans)

    @router.get("/tenants/{tenant_id}")
    async def get_tenant(request: Request, tenant_id: str) -> dict[str, Any]:
        """处理 GET /tenants/{tenant_id} 请求，获取租户。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        authenticator.authorize_admin(request)
        account = await lifecycle.get(tenant_id)
        if account is None:
            raise HTTPException(status_code=404, detail="tenant not found")
        return _account_payload(account, plans)

    @router.post("/tenants/{tenant_id}/suspend")
    async def suspend_tenant(
        request: Request,
        tenant_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /tenants/{tenant_id}/suspend 请求，暂停租户。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        authenticator.authorize_admin(request)
        actor_id = _required_string(body, "actor_id")
        reason = _required_string(body, "reason")
        try:
            account = await lifecycle.suspend(tenant_id, actor_id=actor_id, reason=reason)
        except TenantLifecycleError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _account_payload(account, plans)

    @router.post("/tenants/{tenant_id}/resume")
    async def resume_tenant(
        request: Request,
        tenant_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /tenants/{tenant_id}/resume 请求，恢复租户。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        authenticator.authorize_admin(request)
        actor_id = _required_string(body, "actor_id")
        reason = body.get("reason", "")
        if not isinstance(reason, str):
            raise HTTPException(status_code=422, detail="reason must be a string")
        try:
            account = await lifecycle.resume(tenant_id, actor_id=actor_id, reason=reason)
        except TenantLifecycleError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _account_payload(account, plans)

    @router.post("/tenants/{tenant_id}/cancel")
    async def cancel_tenant(
        request: Request,
        tenant_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /tenants/{tenant_id}/cancel 请求，取消租户。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        authenticator.authorize_admin(request)
        actor_id = _required_string(body, "actor_id")
        reason = _required_string(body, "reason")
        if body.get("confirmation") != tenant_id:
            raise HTTPException(status_code=422, detail="confirmation must match tenant_id")
        try:
            account = await lifecycle.cancel(tenant_id, actor_id=actor_id, reason=reason)
        except TenantLifecycleError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _account_payload(account, plans)

    @router.post("/tenants/{tenant_id}/plan")
    async def change_plan(
        request: Request,
        tenant_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /tenants/{tenant_id}/plan 请求，变更计划。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        authenticator.authorize_admin(request)
        plan_name = _required_string(body, "plan_name")
        actor_id = _required_string(body, "actor_id")
        try:
            account = await lifecycle.change_plan(
                tenant_id,
                plan_name=plan_name,
                actor_id=actor_id,
            )
        except TenantLifecycleError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _account_payload(account, plans)

    @router.post("/tenants/{tenant_id}/usage")
    async def record_usage(
        request: Request,
        tenant_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /tenants/{tenant_id}/usage 请求，记录用量。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        authenticator.authorize_admin(request)
        metric_raw = _required_string(body, "metric")
        try:
            metric = UsageMetric(metric_raw)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="unknown usage metric") from exc
        quantity = body.get("quantity")
        if not isinstance(quantity, int) or quantity <= 0:
            raise HTTPException(status_code=422, detail="quantity must be a positive integer")
        try:
            decision = await usage.record(
                tenant_id=tenant_id,
                metric=metric,
                quantity=quantity,
                source=str(body.get("source") or "platform"),
                idempotency_key=str(body.get("idempotency_key") or ""),
                metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return decision.model_dump(mode="json")

    @router.get("/tenants/{tenant_id}/usage")
    async def usage_summary(
        request: Request,
        tenant_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        """处理 GET /tenants/{tenant_id}/usage 请求，查询用量摘要。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            start: 统计或查询周期的开始时间。
            end: 统计或查询周期的结束时间。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        authenticator.authorize_admin(request)
        try:
            return await usage.summary(
                tenant_id,
                start=_parse_datetime(start),
                end=_parse_datetime(end),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/tenants/{tenant_id}/usage/export")
    async def export_usage(
        request: Request,
        tenant_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> Response:
        """处理 GET /tenants/{tenant_id}/usage/export 请求，导出用量。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            start: 统计或查询周期的开始时间。
            end: 统计或查询周期的结束时间。

        Returns:
            响应结果。
        """
        authenticator.authorize_admin(request)
        summary = await usage.summary(
            tenant_id,
            start=_parse_datetime(start),
            end=_parse_datetime(end),
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["metric", "used", "limit", "unlimited", "ratio", "overage"])
        for metric, values in summary["metrics"].items():
            writer.writerow(
                [
                    metric,
                    values["used"],
                    values["limit"],
                    values["unlimited"],
                    values["ratio"],
                    values["overage"],
                ]
            )
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="usage-{tenant_id}.csv"'},
        )

    @router.get("/tenants/{tenant_id}/usage/alerts")
    async def usage_alerts(
        request: Request,
        tenant_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        """处理 GET /tenants/{tenant_id}/usage/alerts 请求，查询用量告警。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            start: 统计或查询周期的开始时间。
            end: 统计或查询周期的结束时间。

        Returns:
            结构化结果字典。
        """
        authenticator.authorize_admin(request)
        alerts = await usage.alerts(
            tenant_id,
            start=_parse_datetime(start),
            end=_parse_datetime(end),
        )
        return {"alerts": [alert.model_dump(mode="json") for alert in alerts]}

    @router.get("/tenants/{tenant_id}/invoice")
    async def tenant_invoice(
        request: Request,
        tenant_id: str,
        start: str | None = None,
        end: str | None = None,
        format: str = "json",
    ) -> Response:
        """处理 GET /tenants/{tenant_id}/invoice 请求，查询租户发票。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            start: 统计或查询周期的开始时间。
            end: 统计或查询周期的结束时间。
            format: 格式化。

        Returns:
            响应结果。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        authenticator.authorize_admin(request)
        invoice = await usage.invoice(
            tenant_id,
            start=_parse_datetime(start),
            end=_parse_datetime(end),
        )
        if format == "json":
            import json

            return Response(
                content=json.dumps(invoice.model_dump(mode="json"), ensure_ascii=False),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="invoice-{tenant_id}.json"'},
            )
        if format != "csv":
            raise HTTPException(status_code=422, detail="format must be json or csv")
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["invoice_id", "tenant_id", "plan", "metric", "quantity", "amount_cents"])
        for line in invoice.lines:
            writer.writerow(
                [
                    invoice.invoice_id,
                    tenant_id,
                    invoice.plan_name,
                    line.metric.value,
                    line.quantity,
                    line.amount_cents,
                ]
            )
        writer.writerow(
            [invoice.invoice_id, tenant_id, invoice.plan_name, "base", 1, invoice.base_fee_cents]
        )
        writer.writerow(
            [invoice.invoice_id, tenant_id, invoice.plan_name, "total", 1, invoice.total_cents]
        )
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="invoice-{tenant_id}.csv"'},
        )

    @router.get("/operations/overview")
    async def operations_overview(request: Request, limit: int = 100) -> dict[str, Any]:
        """处理 GET /operations/overview 请求，查询操作总览。

        Args:
            request: 当前 HTTP 请求。
            limit: 返回记录的最大数量。

        Returns:
            结构化结果字典。
        """
        authenticator.authorize_admin(request)
        accounts = await lifecycle.list(limit=max(1, min(limit, 500)))
        tenants = []
        alerts: list[dict[str, Any]] = []
        usage_totals = {metric.value: 0 for metric in UsageMetric}
        for account in accounts:
            summary = await usage.summary(account.tenant_id)
            tenant_alerts = await usage.alerts(account.tenant_id)
            alerts.extend(alert.model_dump(mode="json") for alert in tenant_alerts)
            for metric, values in summary["metrics"].items():
                usage_totals[metric] += int(values["used"])
            tenants.append(
                {
                    "tenant_id": account.tenant_id,
                    "name": account.name,
                    "plan_name": account.plan_name,
                    "status": account.status.value,
                    "alerts": len(tenant_alerts),
                }
            )
        failed = await outbox_store.list_failed(limit=100) if outbox_store is not None else []
        return {
            "tenant_count": len(accounts),
            "active_count": sum(1 for account in accounts if account.status == TenantStatus.ACTIVE),
            "suspended_count": sum(
                1 for account in accounts if account.status == TenantStatus.SUSPENDED
            ),
            "cancelled_count": sum(
                1 for account in accounts if account.status == TenantStatus.CANCELLED
            ),
            "usage_totals": usage_totals,
            "alerts": alerts,
            "failed_tasks": failed,
            "tenants": tenants,
        }

    return router


def _account_payload(account, plans: PlanCatalog) -> dict[str, Any]:
    """执行账户载荷。

    Args:
        account: 租户账户。
        plans: 套餐。

    Returns:
        结构化结果字典。
    """
    plan = plans.get(account.plan_name)
    return {
        **account.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"),
    }


def _required_string(body: dict[str, Any], key: str) -> str:
    """校验并返回必填字符串。

    Args:
        body: 请求体数据。
        key: 缓存或配置键。

    Returns:
        字符串结果。

    Raises:
        HTTPException: 请求参数、状态或依赖不满足要求时抛出。
    """
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=422, detail=f"{key} is required")
    return value.strip()


def _parse_datetime(value: str | None) -> datetime | None:
    """解析请求。

    Args:
        value: 待处理值。

    Returns:
        无结果。

    Raises:
        HTTPException: 请求参数、状态或依赖不满足要求时抛出。
    """
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid ISO timestamp") from exc


__all__ = ["create_tenant_control_router"]
