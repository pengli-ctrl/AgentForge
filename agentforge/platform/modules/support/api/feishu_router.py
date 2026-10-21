"""飞书路由模块。"""

from __future__ import annotations

import json
import logging
from typing import Protocol

from fastapi import APIRouter, HTTPException, Query, Request

from agentforge.platform.modules.support.application.service import SupportTicketService
from agentforge.platform.modules.support.connectors.feishu import (
    FeishuEventParser,
    FeishuSignatureVerifier,
)
from agentforge.platform.sdk.ports import ModuleAccessPort

logger = logging.getLogger(__name__)


class FeishuRouterContext(Protocol):
    """飞书上下文能力端口协议。"""

    @property
    def ticket_service(self) -> SupportTicketService:
        """执行工单服务。

        Returns:
            客服工单服务结果。
        """
        ...

    @property
    def module_access(self) -> ModuleAccessPort:
        """返回模块访问。

        Returns:
            模块访问结果。
        """
        ...


def create_feishu_router(
    container: FeishuRouterContext,
    encrypt_key: str = "",
    verification_token: str = "",
    signature_max_age_seconds: float = 0.0,
) -> APIRouter:
    """创建飞书路由。

    Args:
        container: 服务容器。
        encrypt_key: 键。
        verification_token: 核验令牌。
        signature_max_age_seconds: 签名最大。

    Returns:
        处理结果对象。
    """
    router = APIRouter(prefix="/v1/events", tags=["feishu"])
    verifier = FeishuSignatureVerifier(encrypt_key, signature_max_age_seconds)
    parser = FeishuEventParser()
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
        """处理 POST /feishu 请求，接收飞书。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
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

        internal_event = parser.parse(tenant_id, payload)
        if not await container.module_access.is_enabled(tenant_id, "support"):
            raise HTTPException(
                status_code=403,
                detail="Support module is not enabled for tenant",
            )
        ticket = await container.ticket_service.create_from_event(internal_event)
        return ticket.model_dump(mode="json")

    return router
