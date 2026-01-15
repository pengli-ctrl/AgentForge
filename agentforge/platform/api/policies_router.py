"""AgentForge 平台 API 层：policies_router。

本模块定义 policies_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_policies_router。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.application.policy_engine import PolicyEngine
from agentforge.platform.domain.policy import PolicyFileLoader

logger = logging.getLogger(__name__)


def create_policies_router(policy_engine: PolicyEngine | None = None) -> APIRouter:
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        policy_engine: PolicyEngine | None，调用方传入的 policy_engine 参数。

    Returns:
        APIRouter，函数执行后的结果。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
    """
    router = APIRouter(prefix="/v1/policies", tags=["policies"])

    @router.get("")
    async def list_policies(tenant_id: str) -> dict[str, Any]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if policy_engine is None:
            raise HTTPException(status_code=503, detail="policy engine not configured")
        policies = policy_engine.list_policies(tenant_id)
        return {
            "tenant_id": tenant_id,
            "source_revision": policy_engine.source_revision,
            "count": len(policies),
            "policies": [p.model_dump(mode="json") for p in policies],
        }

    @router.get("/revision")
    async def get_revision() -> dict[str, Any]:
        """读取并返回指定数据，并返回调用方需要的结果。

        Returns:
            dict[str, Any]，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if policy_engine is None:
            raise HTTPException(status_code=503, detail="policy engine not configured")
        return {"source_revision": policy_engine.source_revision}

    @router.post("/reload")
    async def reload_policies(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """执行 reload_policies 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            body: dict[str, Any]，调用方传入的 body 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        if policy_engine is None:
            raise HTTPException(status_code=503, detail="policy engine not configured")

        raw = body.get("policies") if isinstance(body.get("policies"), list) else None
        if raw is None:
            raise HTTPException(status_code=422, detail='expected body {"policies": [...]}')

        import json

        try:
            text = json.dumps(raw)
            parsed = PolicyFileLoader.from_string(text)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        old_rev = policy_engine.source_revision
        try:
            new_rev = policy_engine.reload(parsed)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        logger.info(
            "policies reloaded revision %s -> %s (%d policies)",
            old_rev,
            new_rev,
            len(parsed),
        )
        return {
            "revision": new_rev,
            "previous_revision": old_rev,
            "count": len(parsed),
            "source": "http:reload",
        }

    return router
