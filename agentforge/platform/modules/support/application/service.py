"""服务模块。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.evaluation import EvaluationSample
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.modules.support.application.classifier import RuleBasedTicketClassifier
from agentforge.platform.modules.support.application.routing import (
    SupportTicketPolicy,
    parse_datetime,
)
from agentforge.platform.modules.support.domain.ticket import RiskLevel, Ticket, TicketStatus
from agentforge.platform.modules.support.ports import ReplyConnectorPort, TicketRepository
from agentforge.platform.sdk.ports import AuditPort, EvaluationPort


class SupportTicketService:
    """客服工单应用服务，编排领域用例及其副作用。"""

    def __init__(
        self,
        repository: TicketRepository,
        classifier: RuleBasedTicketClassifier,
        reply_connector: ReplyConnectorPort | None = None,
        audit_repository: AuditPort | None = None,
        evaluation_repository: EvaluationPort | None = None,
        ticket_policy: SupportTicketPolicy | None = None,
    ) -> None:
        """初始化 SupportTicketService。

        Args:
            repository: 数据仓储实现。
            classifier: 分类器。
            reply_connector: 回复连接器。
            audit_repository: 审计仓储。
            evaluation_repository: 评估仓储。
            ticket_policy: 工单策略。
        """
        self._repository = repository
        self._classifier = classifier
        self._reply_connector = reply_connector
        self._audit_repository = audit_repository
        self._evaluation_repository = evaluation_repository
        self._ticket_policy = ticket_policy

    async def create_from_event(self, event: dict[str, Any]) -> Ticket:
        """创建从事件。

        Args:
            event: 待处理事件。

        Returns:
            工单结果。
        """
        tenant_id = self._require(event, "tenant_id")
        source = self._require(event, "source")
        message_id = self._require(event, "message_id")
        text = self._require(event, "text")
        existing = await self._repository.get_by_idempotency_key(tenant_id, message_id)
        if existing is not None:
            return existing
        extra_metadata = event.get("metadata")
        extra_metadata = dict(extra_metadata) if isinstance(extra_metadata, dict) else {}
        ticket = Ticket(
            ticket_id=str(uuid4()),
            tenant_id=tenant_id,
            customer_id=event.get("customer_id"),
            conversation_id=event.get("conversation_id") or event.get("reply_target"),
            source=source,
            subject=text[:120],
            idempotency_key=message_id,
            metadata={
                "message_id": message_id,
                "raw_message": text,
                "reply_target": event.get("reply_target"),
                **extra_metadata,
            },
        )
        ticket.transition_to(TicketStatus.CLASSIFYING)
        result = await self._classifier.classify(text)
        ticket.intent = result.intent
        ticket.priority = result.priority
        ticket.product = result.product
        ticket.assigned_team = result.assigned_team
        ticket.risk_level = result.risk_level
        ticket.confidence = result.confidence
        if self._ticket_policy is not None:
            routing = event.get("routing")
            policy = await self._ticket_policy.for_tenant(tenant_id)
            policy.apply(
                ticket,
                source=source,
                routing=routing if isinstance(routing, dict) else None,
            )
        if result.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            ticket.transition_to(TicketStatus.WAITING_APPROVAL)
        else:
            ticket.transition_to(TicketStatus.WAITING_REVIEW)
        trace_id = str(uuid4())
        await self._repository.save(
            ticket,
            events=[self._make_event("ticket.created", ticket, trace_id)],
        )
        await self._record_audit(
            action="ticket.created",
            ticket=ticket,
            actor_type="system",
            actor_id="support-ticket-service",
            trace_id=trace_id,
            payload={
                "source": source,
                "status": ticket.status.value,
                "assigned_team": ticket.assigned_team,
                "assignee_id": ticket.assignee_id,
                "notification_target": ticket.metadata.get("notification_target"),
                "priority": ticket.priority.value,
                "queue": ticket.metadata.get("queue"),
            },
        )
        return ticket

    async def apply_approval(
        self, tenant_id: str, ticket_id: str, decision: str, decided_by: str
    ) -> Ticket:
        """应用审批。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            ticket_id: 工单 ID。
            decision: 待处理的授权或审批决策。
            decided_by: 由。

        Returns:
            工单结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        ticket = await self._repository.get(tenant_id, ticket_id)
        if ticket is None:
            raise ValueError("Ticket not found")
        if decision not in {"approve", "reject"}:
            raise ValueError("Unsupported approval decision")
        if decision == "approve" and ticket.status == TicketStatus.READY_TO_PUBLISH:
            return ticket
        if decision == "reject" and ticket.status == TicketStatus.ESCALATED:
            return ticket
        if ticket.status != TicketStatus.WAITING_APPROVAL:
            raise ValueError("Ticket is not waiting for approval")
        if decision == "approve":
            ticket.transition_to(TicketStatus.READY_TO_PUBLISH)
        else:
            ticket.transition_to(TicketStatus.ESCALATED)
        ticket.metadata["approval"] = {"decision": decision, "decided_by": decided_by}
        trace_id = str(uuid4())
        await self._repository.save(
            ticket,
            events=[self._make_event("approval.completed", ticket, trace_id)],
        )
        await self._record_audit(
            action="approval.completed",
            ticket=ticket,
            actor_type="user",
            actor_id=decided_by,
            trace_id=trace_id,
            payload={"decision": decision, "status": ticket.status.value},
        )
        return ticket

    async def review_draft(
        self,
        tenant_id: str,
        ticket_id: str,
        action: str,
        reviewer_id: str,
        edited_text: str | None = None,
        reason: str | None = None,
    ) -> Ticket:
        """审核草稿。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            ticket_id: 工单 ID。
            action: 待执行动作名称。
            reviewer_id: 审核人 ID。
            edited_text: 文本。
            reason: 变更原因。

        Returns:
            工单结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        ticket = await self._repository.get(tenant_id, ticket_id)
        if ticket is None:
            raise ValueError("Ticket not found")
        if action not in {"accept", "edit", "reject"}:
            raise ValueError("Unsupported review action")
        if ticket.status == TicketStatus.READY_TO_PUBLISH and action in {"accept", "edit"}:
            return ticket
        if ticket.status == TicketStatus.ESCALATED and action == "reject":
            return ticket
        if ticket.status != TicketStatus.WAITING_REVIEW:
            raise ValueError("Ticket is not waiting for review")

        draft = ticket.metadata.get("draft")
        draft_payload = draft if isinstance(draft, dict) else {}
        original_draft_text = str(draft_payload.get("reply_text", ""))
        review = {"action": action, "reviewer_id": reviewer_id}
        if action == "edit":
            if not isinstance(edited_text, str) or not edited_text.strip():
                raise ValueError("edited_text is required for edit")
            if not isinstance(draft, dict):
                raise ValueError("Ticket has no draft to edit")
            draft["reply_text"] = edited_text.strip()
            review["edited_text"] = edited_text.strip()
            ticket.transition_to(TicketStatus.READY_TO_PUBLISH)
            event_type = "ticket.review.edited"
        elif action == "accept":
            ticket.transition_to(TicketStatus.READY_TO_PUBLISH)
            event_type = "ticket.review.accepted"
        else:
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("reason is required for reject")
            review["reason"] = reason.strip()
            ticket.transition_to(TicketStatus.ESCALATED)
            event_type = "ticket.review.rejected"

        ticket.metadata["review"] = review
        trace_id = str(uuid4())
        await self._repository.save(
            ticket,
            events=[self._make_event(event_type, ticket, trace_id)],
        )
        await self._record_audit(
            action=event_type,
            ticket=ticket,
            actor_type="user",
            actor_id=reviewer_id,
            trace_id=trace_id,
            payload=review,
        )
        final_draft = ticket.metadata.get("draft")
        final_text = (
            str(final_draft.get("reply_text", ""))
            if isinstance(final_draft, dict)
            else original_draft_text
        )
        await self._record_evaluation_sample(
            ticket=ticket,
            action=action,
            reviewer_id=reviewer_id,
            original_draft_text=original_draft_text,
            final_text=final_text,
            reason=str(review.get("reason", "")),
            trace_id=trace_id,
            model_name=str(draft_payload.get("model_name", "")),
            provider=str(draft_payload.get("provider", "")),
        )
        return ticket

    async def publish_reply(
        self,
        tenant_id: str,
        ticket_id: str,
        text: str | None = None,
    ) -> Ticket:
        """发布回复。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            ticket_id: 工单 ID。
            text: 待处理文本。

        Returns:
            工单结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        ticket = await self._repository.get(tenant_id, ticket_id)
        if ticket is None:
            raise ValueError("Ticket not found")
        if ticket.status == TicketStatus.PUBLISHED:
            return ticket
        if ticket.status != TicketStatus.READY_TO_PUBLISH:
            raise ValueError("Ticket is not ready to publish")
        if self._reply_connector is None:
            raise ValueError("Reply connector is not configured")

        if text is None:
            draft = ticket.metadata.get("draft")
            text = draft.get("reply_text") if isinstance(draft, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Reply text is required")
        text = text.strip()

        target = str(ticket.metadata.get("reply_target") or ticket.conversation_id or "")
        if not target:
            raise ValueError("Reply target is missing")
        response = await self._reply_connector.send_text(
            target=target,
            text=text,
            idempotency_key=f"reply-{ticket.ticket_id}",
        )
        ticket.metadata["reply"] = {
            "message_id": response.get("message_id", ""),
            "text": text,
        }
        ticket.transition_to(TicketStatus.PUBLISHED)
        if self._ticket_policy is not None:
            self._ticket_policy.close_sla(ticket, outcome="published")
        trace_id = str(uuid4())
        await self._repository.save(
            ticket,
            events=[self._make_event("reply.published", ticket, trace_id)],
        )
        await self._record_audit(
            action="reply.published",
            ticket=ticket,
            actor_type="system",
            actor_id="support-ticket-service",
            trace_id=trace_id,
            payload={"message_id": ticket.metadata["reply"]["message_id"]},
        )
        return ticket

    async def sweep_sla(self, now: datetime | None = None) -> dict[str, Any]:
        """扫描SLA。

        Args:
            now: 输入参数。

        Returns:
            结构化结果字典。
        """
        if self._ticket_policy is None:
            return {"scanned": 0, "due_soon": 0, "breached": 0, "escalated": 0}
        current = now or datetime.now(timezone.utc)
        due_soon = breached = escalated = 0
        events: list[dict[str, Any]] = []
        tenant_policies: dict[str, Any] = {}
        tickets = await self._repository.list_all(limit=10_000)
        for ticket in tickets:
            if ticket.status in {TicketStatus.PUBLISHED, TicketStatus.CANCELLED}:
                continue
            sla = ticket.metadata.get("sla")
            if not isinstance(sla, dict) or sla.get("status") != "open":
                continue
            due_at = parse_datetime(sla.get("due_at"))
            if due_at is None:
                continue
            policy = tenant_policies.get(ticket.tenant_id)
            if policy is None:
                policy = await self._ticket_policy.for_tenant(ticket.tenant_id)
                tenant_policies[ticket.tenant_id] = policy
            remaining = (due_at - current).total_seconds()
            ticket_events: list[EventEnvelope] = []
            actions: list[str] = []
            if 0 < remaining <= policy.due_soon_seconds:
                if not sla.get("due_soon_notified_at"):
                    sla["due_soon_notified_at"] = current.isoformat()
                    ticket_events.append(self._make_sla_event(ticket, "due_soon", due_at, current))
                    actions.append("ticket.sla_due_soon")
                    due_soon += 1
            elif remaining <= 0 and not sla.get("breach_notified_at"):
                sla["breach_notified_at"] = current.isoformat()
                actions.append("ticket.sla_breached")
                breached += 1
                if ticket.can_transition_to(TicketStatus.ESCALATED):
                    previous_assignee = ticket.assignee_id
                    if policy.sla_escalation_assignee:
                        ticket.assignee_id = policy.sla_escalation_assignee
                        sla["escalated_from_assignee"] = previous_assignee
                        sla["escalated_to_assignee"] = ticket.assignee_id
                    ticket.transition_to(TicketStatus.ESCALATED)
                    sla["escalated_at"] = current.isoformat()
                    actions.append("ticket.sla_escalated")
                    escalated += 1
                ticket_events.append(self._make_sla_event(ticket, "breached", due_at, current))
            if not ticket_events:
                continue
            ticket.metadata["sla"] = sla
            await self._repository.save(ticket, events=ticket_events)
            trace_id = ticket_events[0].trace_id
            for action in actions:
                await self._record_audit(
                    action=action,
                    ticket=ticket,
                    actor_type="system",
                    actor_id="support-sla-sweeper",
                    trace_id=trace_id,
                    payload={
                        "due_at": due_at.isoformat(),
                        "queue": ticket.metadata.get("queue"),
                        "assignee_id": ticket.assignee_id,
                    },
                )
            events.extend(
                [
                    {
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "ticket_id": ticket.ticket_id,
                    }
                    for event in ticket_events
                ]
            )
        return {
            "scanned": len(tickets),
            "due_soon": due_soon,
            "breached": breached,
            "escalated": escalated,
            "events": events,
        }

    def _make_sla_event(
        self,
        ticket: Ticket,
        state: str,
        due_at: datetime,
        occurred_at: datetime,
    ) -> EventEnvelope:
        """构造SLA事件。

        Args:
            ticket: 客服工单对象。
            state: 当前状态。
            due_at: 到期时间。
            occurred_at: 用量发生时间。

        Returns:
            事件结果。
        """
        event_id = str(
            uuid5(
                NAMESPACE_URL,
                f"support-sla:{ticket.ticket_id}:{state}:{due_at.isoformat()}",
            )
        )
        return EventEnvelope(
            event_id=event_id,
            event_type=f"support.ticket.sla_{state}.v1",
            tenant_id=ticket.tenant_id,
            task_id=ticket.ticket_id,
            trace_id=event_id,
            producer="support-sla-sweeper",
            payload={
                "ticket_id": ticket.ticket_id,
                "queue": ticket.metadata.get("queue"),
                "assigned_team": ticket.assigned_team,
                "assignee_id": ticket.assignee_id,
                "notification_target": ticket.metadata.get("notification_target"),
                "priority": ticket.priority.value,
                "due_at": due_at.isoformat(),
                "occurred_at": occurred_at.isoformat(),
                "status": ticket.status.value,
            },
        )

    async def resolve_invoice_gate_alert(self, event: dict[str, Any]) -> Ticket:
        """解析发票门禁告警。

        Args:
            event: 待处理事件。

        Returns:
            工单结果。
        """
        tenant_id = self._require(event, "tenant_id")
        alert_id = self._require(event, "alert_id")
        alert_type = str(event.get("alert_type") or "invoice_gate_alert")
        reason = str(event.get("resolution") or "condition_cleared")
        resolved_at = str(event.get("resolved_at") or "")
        ticket = await self._repository.get_by_idempotency_key(tenant_id, alert_id)
        if ticket is None:
            # 重试后，问题解决事件可能早于其原始事件到达；
            # 创建取消墓碑可防止后续事件重新打开工单。
            ticket = await self.create_from_event(
                {
                    "tenant_id": tenant_id,
                    "source": str(event.get("source") or "expense-invoice-gate"),
                    "message_id": alert_id,
                    "text": str(event.get("text") or f"Invoice gate alert {alert_type} resolved"),
                    "metadata": {
                        "alert_type": alert_type,
                        "alert_id": alert_id,
                        "claim_id": event.get("claim_id"),
                        "actor_id": event.get("actor_id"),
                        "expense_event_id": event.get("event_id"),
                    },
                }
            )
        if ticket.status == TicketStatus.CANCELLED:
            return ticket
        if not ticket.can_transition_to(TicketStatus.CANCELLED):
            return ticket
        ticket.transition_to(TicketStatus.CANCELLED)
        if self._ticket_policy is not None:
            self._ticket_policy.close_sla(ticket, outcome="cancelled")
        ticket.metadata["resolution"] = {
            "reason": reason,
            "resolved_at": resolved_at,
            "alert_type": alert_type,
        }
        trace_id = str(event.get("trace_id") or uuid4())
        await self._repository.save(
            ticket,
            events=[self._make_event("ticket.alert_resolved", ticket, trace_id)],
        )
        await self._record_audit(
            action="ticket.alert_resolved",
            ticket=ticket,
            actor_type="system",
            actor_id="expense-invoice-service",
            trace_id=trace_id,
            payload={
                "alert_id": alert_id,
                "alert_type": alert_type,
                "reason": reason,
                "resolved_at": resolved_at,
            },
        )
        return ticket

    @staticmethod
    def _make_event(event_type: str, ticket: Ticket, trace_id: str | None = None) -> EventEnvelope:
        """构造事件。

        Args:
            event_type: 事件类型。
            ticket: 客服工单对象。
            trace_id: 链路追踪 ID。

        Returns:
            事件结果。
        """
        return EventEnvelope(
            event_id=str(uuid4()),
            event_type=event_type,
            tenant_id=ticket.tenant_id,
            task_id=ticket.ticket_id,
            trace_id=trace_id or str(uuid4()),
            producer="support-ticket-service",
            payload={"ticket_id": ticket.ticket_id, "status": ticket.status.value},
        )

    async def _record_audit(
        self,
        action: str,
        ticket: Ticket,
        actor_type: str,
        actor_id: str,
        trace_id: str,
        payload: dict[str, Any],
    ) -> None:
        """记录审计。

        Args:
            action: 待执行动作名称。
            ticket: 客服工单对象。
            actor_type: 参与者类型。
            actor_id: 执行操作的参与者 ID。
            trace_id: 链路追踪 ID。
            payload: 事件、工作流或请求载荷。
        """
        if self._audit_repository is None:
            return
        await self._audit_repository.save(
            AuditEvent(
                event_id=str(uuid4()),
                tenant_id=ticket.tenant_id,
                action=action,
                resource_type="ticket",
                resource_id=ticket.ticket_id,
                risk_level=ticket.risk_level,
                actor_type=actor_type,
                actor_id=actor_id,
                trace_id=trace_id,
                payload=payload,
            )
        )

    async def _record_evaluation_sample(
        self,
        ticket: Ticket,
        action: str,
        reviewer_id: str,
        original_draft_text: str,
        final_text: str,
        reason: str,
        trace_id: str,
        model_name: str,
        provider: str,
    ) -> None:
        """记录评估样本。

        Args:
            ticket: 客服工单对象。
            action: 待执行动作名称。
            reviewer_id: 审核人 ID。
            original_draft_text: 草稿文本。
            final_text: 最终文本。
            reason: 变更原因。
            trace_id: 链路追踪 ID。
            model_name: 模型名称。
            provider: 提供方。
        """
        if self._evaluation_repository is None:
            return
        await self._evaluation_repository.save(
            EvaluationSample(
                sample_id=str(uuid4()),
                tenant_id=ticket.tenant_id,
                source_ticket_id=ticket.ticket_id,
                query=str(ticket.metadata.get("raw_message") or ticket.subject),
                draft_text=original_draft_text,
                final_text=final_text,
                action=action,
                reason=reason,
                reviewer_id=reviewer_id,
                intent=ticket.intent,
                priority=ticket.priority,
                risk_level=ticket.risk_level,
                model_name=model_name,
                provider=provider,
                trace_id=trace_id,
            )
        )

    @staticmethod
    def _require(event: dict[str, Any], key: str) -> str:
        """执行校验。

        Args:
            event: 待处理事件。
            key: 缓存或配置键。

        Returns:
            字符串结果。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        value = event.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing required event field: {key}")
        return value.strip()
