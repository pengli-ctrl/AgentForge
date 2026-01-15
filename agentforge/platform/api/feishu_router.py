"""AgentForge 平台 API 层：feishu_router。

本模块定义 feishu_ 相关 HTTP 接口，负责请求解析、鉴权校验、调用应用服务并组织响应。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要函数：create_feishu_router。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request

from agentforge.platform.connectors.feishu import FeishuEventParser, FeishuSignatureVerifier
from agentforge.platform.runtime import ServiceContainer

logger = logging.getLogger(__name__)


def create_feishu_router(
    container: ServiceContainer,
    encrypt_key: str = "",
    verification_token: str = "",
    signature_max_age_seconds: float = 0.0,
) -> APIRouter:
    """创建新的业务对象，并返回调用方需要的结果。

    Args:
        container: ServiceContainer，调用方传入的 container 参数。
        encrypt_key: str，调用方传入的 encrypt_key 参数。
        verification_token: str，调用方传入的 verification_token 参数。
        signature_max_age_seconds: float，调用方传入的 signature_max_age_seconds 参数。

    Returns:
        APIRouter，函数执行后的结果。

    Raises:
        HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
    """
    router = APIRouter(prefix="/v1/events", tags=["feishu"])
    verifier = FeishuSignatureVerifier(encrypt_key, signature_max_age_seconds)
    parser = FeishuEventParser()
    # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
    # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
    signature_verification_enabled = verifier.configured
    if not signature_verification_enabled:
        logger.warning(
            "Feishu signature verification DISABLED: no encrypt_key configured. "
            "Inbound /v1/events/feishu activity will not be authenticated."
        )

    @router.post("/feishu")
    async def receive_feishu(
        request: Request,
        tenant_id: str = Query(...),
    ) -> dict:
        """执行 receive_feishu 对应的逻辑，并返回处理结果。

        Args:
            request: Request，调用方传入的 request 参数。
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。

        Raises:
            HTTPException: 当输入、状态或外部依赖不满足要求时抛出。
        """
        raw_body = await request.body()
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

        if payload.get("type") == "url_verification":
            if verification_token and payload.get("token") != verification_token:
                raise HTTPException(status_code=401, detail="Invalid verification token")
            return {"challenge": payload.get("challenge", "")}

        timestamp = request.headers.get("X-Lark-Request-Timestamp", "")
        nonce = request.headers.get("X-Lark-Request-Nonce", "")
        signature = request.headers.get("X-Lark-Signature", "")

        if signature_verification_enabled:
            if not verifier.verify(timestamp, nonce, raw_body, signature):
                raise HTTPException(status_code=401, detail="Invalid Feishu signature")
        # 验证禁用状态下策略和功能不会意外生效。
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。

        internal_event = parser.parse(tenant_id, payload)
        ticket = await container.ticket_service.create_from_event(internal_event)
        return ticket.model_dump(mode="json")

    return router
