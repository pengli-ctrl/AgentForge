"""策略路由模块。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from agentforge.platform.application.policy_engine import PolicyEngine
from agentforge.platform.domain.policy import PolicyFileLoader

logger = logging.getLogger(__name__)


def create_policies_router(policy_engine: PolicyEngine | None = None) -> APIRouter:
    """创建策略路由。

    Args:
        policy_engine: 策略引擎。

    Returns:
        处理结果对象。
    """
    router = APIRouter(prefix="/v1/policies", tags=["policies"])

    @router.get("")
    async def list_policies(tenant_id: str) -> dict[str, Any]:
        """处理 GET 请求，查询策略。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
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
        """获取当前策略修订版本。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        if policy_engine is None:
            raise HTTPException(status_code=503, detail="policy engine not configured")
        return {"source_revision": policy_engine.source_revision}

    @router.post("/reload")
    async def reload_policies(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """处理 POST /reload 请求，重新加载策略。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
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
