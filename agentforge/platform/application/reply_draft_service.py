"""AgentForge 平台应用服务层：reply_draft_service。

本模块实现 reply_draft_service 应用服务，编排多个领域对象和基础设施组件完成业务流程。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：ReplyDraftService。
"""

from __future__ import annotations

from agentforge.platform.application.ports import ModelGateway
from agentforge.platform.domain.knowledge import RetrievedChunk
from agentforge.platform.domain.model import DraftResult, ModelRequest
from agentforge.platform.domain.ticket import Ticket


class ReplyDraftService:
    """ReplyDraftService。

    ReplyDraftService 编排业务流程，协调仓储、模型、策略和外部连接器完成用例。

    主要成员：
    - 方法 create_draft()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, model_gateway: ModelGateway) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            model_gateway: ModelGateway，调用方传入的 model_gateway 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._model_gateway = model_gateway

    async def create_draft(
        self,
        ticket: Ticket,
        chunks: list[RetrievedChunk],
        trace_id: str = "",
    ) -> DraftResult:
        """创建新的业务对象，并返回调用方需要的结果。

        Args:
            ticket: Ticket，调用方传入的 ticket 参数。
            chunks: list[RetrievedChunk]，调用方传入的 chunks 参数。
            trace_id: str，调用方传入的 trace_id 参数。

        Returns:
            DraftResult，函数执行后的结果。
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
