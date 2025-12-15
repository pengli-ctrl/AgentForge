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
    router = APIRouter(prefix="/v1/events", tags=["feishu"])
    verifier = FeishuSignatureVerifier(encrypt_key, signature_max_age_seconds)
    parser = FeishuEventParser()
    # Fail-closed note: the router never claims a payload was signature-verified
    # unless an Encrypt-Key is configured and verification actually succeeded.
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
        # When verification is disabled (no encrypt_key) we do NOT claim the
        # event was signed; it is processed as best-effort/dev traffic.

        internal_event = parser.parse(tenant_id, payload)
        ticket = await container.ticket_service.create_from_event(internal_event)
        return ticket.model_dump(mode="json")

    return router
