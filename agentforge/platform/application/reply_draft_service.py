from __future__ import annotations

from agentforge.platform.application.ports import ModelGateway
from agentforge.platform.domain.knowledge import RetrievedChunk
from agentforge.platform.domain.model import DraftResult, ModelRequest
from agentforge.platform.domain.ticket import Ticket


class ReplyDraftService:
    def __init__(self, model_gateway: ModelGateway) -> None:
        self._model_gateway = model_gateway

    async def create_draft(self, ticket: Ticket, chunks: list[RetrievedChunk]) -> DraftResult:
        if not chunks:
            return DraftResult(
                reply_text="No approved knowledge was found. Escalate to a human agent.",
                confidence=0.0,
                requires_approval=True,
            )

        allowed_citations = [chunk.chunk_id for chunk in chunks]
        context = "\n\n".join(
            f"[{chunk.chunk_id}] {chunk.title}: {chunk.content}" for chunk in chunks
        )
        response = await self._model_gateway.complete(
            ModelRequest(
                system_prompt=(
                    "Draft a customer support reply. Only use the provided context. "
                    "Return citations as chunk identifiers."
                ),
                user_prompt=f"Ticket: {ticket.subject}\n\nContext:\n{context}",
                metadata={"allowed_citations": allowed_citations},
            )
        )
        invalid_citations = set(response.citations) - set(allowed_citations)
        if invalid_citations or not response.citations:
            return DraftResult(
                reply_text="Unable to produce a verifiable draft. Escalate to a human agent.",
                confidence=0.0,
                requires_approval=True,
                model_name=response.model,
                provider=response.provider,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_amount=response.cost_amount,
            )
        return DraftResult(
            reply_text=response.content,
            citations=response.citations,
            confidence=0.85,
            requires_approval=False,
            model_name=response.model,
            provider=response.provider,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_amount=response.cost_amount,
        )
