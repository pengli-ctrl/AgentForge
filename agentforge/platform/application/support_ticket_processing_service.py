"""AgentForge 平台应用服务层：support_ticket_processing_service。

本模块实现 support_ticket_processing_service 应用服务，编排多个领域对象和基础设施组件完成业务流程。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：SupportTicketProcessingService。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from agentforge.platform.application.knowledge_service import KnowledgeService
from agentforge.platform.application.ports import AuditRepository, CostRepository, TicketRepository
from agentforge.platform.application.reply_draft_service import ReplyDraftService
from agentforge.platform.application.support_ticket_service import SupportTicketService
from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.cost import CostRecord
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.ticket import Ticket, TicketStatus
from agentforge.platform.observability.tracing import start_span


class SupportTicketProcessingService:
    """SupportTicketProcessingService。

    SupportTicketProcessingService 编排业务流程，协调仓储、模型、策略和外部连接器完成用例。

    主要成员：
    - 方法 process_event()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        ticket_service: SupportTicketService,
        ticket_repository: TicketRepository,
        knowledge_service: KnowledgeService,
        reply_draft_service: ReplyDraftService,
        cost_repository: CostRepository,
        audit_repository: AuditRepository | None = None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            ticket_service: SupportTicketService，调用方传入的 ticket_service 参数。
            ticket_repository: TicketRepository，调用方传入的 ticket_repository 参数。
            knowledge_service: KnowledgeService，调用方传入的 knowledge_service 参数。
            reply_draft_service: ReplyDraftService，调用方传入的 reply_draft_service 参数。
            cost_repository: CostRepository，调用方传入的 cost_repository 参数。
            audit_repository: AuditRepository | None，调用方传入的 audit_repository 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._ticket_service = ticket_service
        self._ticket_repository = ticket_repository
        self._knowledge_service = knowledge_service
        self._reply_draft_service = reply_draft_service
        self._cost_repository = cost_repository
        self._audit_repository = audit_repository

    async def process_event(self, event: dict[str, Any]) -> Ticket:
        """处理业务流程，并返回调用方需要的结果。

        Args:
            event: dict[str, Any]，调用方传入的 event 参数。

        Returns:
            Ticket，函数执行后的结果。
        """
        with start_span("support_ticket.process") as span:
            if span and span.is_recording():
                span.set_attribute("tenant_id", str(event.get("tenant_id", "")))
            return await self._process_event(event, span)

    async def _process_event(self, event: dict[str, Any], span) -> Ticket:
        """执行 _process_event 对应的逻辑，并返回处理结果。

        Args:
            event: dict[str, Any]，调用方传入的 event 参数。
            span: Any，调用方传入的 span 参数。

        Returns:
            Ticket，函数执行后的结果。
        """
        ticket = await self._ticket_service.create_from_event(event)
        chunks = await self._knowledge_service.search(ticket.tenant_id, ticket.subject, limit=5)
        trace_id = str(uuid4())
        draft = await self._reply_draft_service.create_draft(ticket, chunks, trace_id=trace_id)
        ticket.metadata["retrieval"] = [chunk.model_dump(mode="json") for chunk in chunks]
        ticket.metadata["draft"] = draft.model_dump(mode="json")

        if draft.requires_approval and ticket.status == TicketStatus.WAITING_REVIEW:
            ticket.transition_to(TicketStatus.WAITING_APPROVAL)

        event_envelope = EventEnvelope(
            event_id=str(uuid4()),
            event_type="ticket.drafted",
            tenant_id=ticket.tenant_id,
            task_id=ticket.ticket_id,
            trace_id=trace_id,
            producer="support-ticket-processing-service",
            payload={
                "ticket_id": ticket.ticket_id,
                "citation_count": len(draft.citations),
                "requires_approval": draft.requires_approval,
            },
        )
        await self._ticket_repository.save(ticket, events=[event_envelope])

        if self._audit_repository is not None:
            await self._audit_repository.save(
                AuditEvent(
                    event_id=str(uuid4()),
                    tenant_id=ticket.tenant_id,
                    action="ticket.drafted",
                    resource_type="ticket",
                    resource_id=ticket.ticket_id,
                    risk_level=ticket.risk_level,
                    actor_id="support-ticket-processing-service",
                    trace_id=trace_id,
                    payload={
                        "citation_count": len(draft.citations),
                        "requires_approval": draft.requires_approval,
                        "model_name": draft.model_name,
                        "provider": draft.provider,
                        "cost_amount": draft.cost_amount,
                    },
                )
            )

        if draft.model_name:
            await self._cost_repository.save(
                CostRecord(
                    tenant_id=ticket.tenant_id,
                    task_id=ticket.ticket_id,
                    model_name=draft.model_name,
                    provider=draft.provider,
                    input_tokens=draft.input_tokens,
                    output_tokens=draft.output_tokens,
                    amount=draft.cost_amount,
                )
            )
        if span and span.is_recording():
            span.set_attribute("task_id", ticket.ticket_id)
            span.set_attribute("ticket_status", ticket.status.value)
            span.set_attribute("citation_count", len(draft.citations))
            span.set_attribute("model_name", draft.model_name)
            span.set_attribute("cost_amount", draft.cost_amount)
        return ticket
