from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request

from agentforge.platform.connectors.feishu import FeishuEventParser, FeishuSignatureVerifier
from agentforge.platform.runtime import ServiceContainer


def create_feishu_router(
    container: ServiceContainer,
    encrypt_key: str = "",
    verification_token: str = "",
) -> APIRouter:
    router = APIRouter(prefix="/v1/events", tags=["feishu"])
    verifier = FeishuSignatureVerifier(encrypt_key)
    parser = FeishuEventParser()

    @router.post("/feishu")
    async def receive_feishu(
        request: Request,
        tenant_id: str = Query(...),
    ) -> dict:
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
        if encrypt_key and not verifier.verify(timestamp, nonce, raw_body, signature):
            raise HTTPException(status_code=401, detail="Invalid Feishu signature")

        internal_event = parser.parse(tenant_id, payload)
        ticket = await container.ticket_service.create_from_event(internal_event)
        return ticket.model_dump(mode="json")

    return router
