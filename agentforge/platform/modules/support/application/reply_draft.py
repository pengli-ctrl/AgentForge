"""回复草稿模块。"""

from __future__ import annotations

from agentforge.platform.domain.knowledge import RetrievedChunk
from agentforge.platform.domain.model import DraftResult, ModelRequest
from agentforge.platform.modules.support.domain.ticket import Ticket
from agentforge.platform.sdk.ports import ModelGatewayPort


class ReplyDraftService:
    """回复草稿应用服务，编排领域用例及其副作用。"""

    def __init__(self, model_gateway: ModelGatewayPort) -> None:
        """初始化 ReplyDraftService。

        Args:
            model_gateway: 模型网关。
        """
        self._model_gateway = model_gateway

    async def create_draft(
        self,
        ticket: Ticket,
        chunks: list[RetrievedChunk],
        trace_id: str = "",
    ) -> DraftResult:
        """创建草稿。

        Args:
            ticket: 客服工单对象。
            chunks: 文本分片列表。
            trace_id: 链路追踪 ID。

        Returns:
            草稿结果结果。
        """
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
        metadata: dict[str, object] = {"allowed_citations": allowed_citations}
        if trace_id:
            metadata["trace_id"] = trace_id
        metadata["tenant_id"] = ticket.tenant_id
        response = await self._model_gateway.complete(
            ModelRequest(
                system_prompt=(
                    "Draft a customer support reply. Only use the provided context. "
                    "Return citations as chunk identifiers."
                ),
                user_prompt=f"Ticket: {ticket.subject}\n\nContext:\n{context}",
                metadata=metadata,
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
