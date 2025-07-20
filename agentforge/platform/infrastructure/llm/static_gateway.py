from __future__ import annotations

from agentforge.platform.domain.model import ModelRequest, ModelResponse


class StaticModelGateway:
    async def complete(self, request: ModelRequest) -> ModelResponse:
        citations = list(request.metadata.get("allowed_citations", []))
        return ModelResponse(
            content="Draft response generated from approved knowledge.",
            model="static-local",
            provider="local",
            input_tokens=len(request.user_prompt.split()),
            output_tokens=8,
            cost_amount=0.0,
            citations=citations,
        )
