"""写回模块。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.authorization import AuthorizationOutcome
from agentforge.platform.domain.connector import ConnectorContext
from agentforge.platform.modules.support.domain.ticket import Ticket
from agentforge.platform.modules.support.ports import HighRiskAuthorizerPort
from agentforge.platform.sdk.ports import AuditPort, ConnectorCatalogPort

Resolver = Callable[[str], str | None]


class TicketWritebackService:
    """工单写回应用服务，编排领域用例及其副作用。"""

    def __init__(
        self,
        registry: ConnectorCatalogPort,
        audit_repository: AuditPort | None = None,
        connector_resolver: Callable[[str], str | None] | None = None,
        high_risk_authorizer: HighRiskAuthorizerPort | None = None,
    ) -> None:
        """初始化 TicketWritebackService。

        Args:
            registry: 注册表实例。
            audit_repository: 审计仓储。
            connector_resolver: 连接器解析器。
            high_risk_authorizer: 高风险授权器。
        """
        self._registry = registry
        self._audit_repository = audit_repository
        self._connector_resolver = connector_resolver
        self._high_risk_authorizer = high_risk_authorizer

    async def _check_authorization(self, ticket: Ticket, action: str, actor: str) -> None:
        """检查授权。

        Args:
            ticket: 客服工单对象。
            action: 待执行动作名称。
            actor: 输入参数。

        Raises:
            PermissionError: 调用方缺少所需权限时抛出。
        """
        if self._high_risk_authorizer is None:
            return
        decision = await self._high_risk_authorizer.authorize(
            tenant_id=ticket.tenant_id,
            principal=actor,
            action=action,
            resource_type="ticket",
            resource_id=ticket.ticket_id,
            ticket=ticket,
        )
        if decision.outcome != AuthorizationOutcome.ALLOWED:
            raise PermissionError("; ".join(decision.reasons))

    async def write_back(
        self,
        ticket: Ticket,
        action: str = "ticket.writeback",
        *,
        actor: str = "support-writeback",
    ) -> dict[str, Any]:
        """写入返回。

        Args:
            ticket: 客服工单对象。
            action: 待执行动作名称。
            actor: 输入参数。

        Returns:
            结构化结果字典。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        await self._check_authorization(ticket, action, actor)
        connector_id = self._resolve_connector(ticket.tenant_id)
        if connector_id is None:
            raise ValueError("No write-back connector registered for tenant")

        payload = self._build_payload(ticket)
        context = ConnectorContext(
            tenant_id=ticket.tenant_id,
            task_id=ticket.ticket_id,
            idempotency_key=f"wb-{ticket.ticket_id}",
            trace_id=str(uuid4()),
            actor=actor,
        )
        result = await self._registry.invoke(
            connector_id,
            action,
            payload,
            context,
        )
        await self._record_audit(ticket, action, result, context.trace_id)
        if not result.ok:
            raise RuntimeError(result.error or "write-back failed")
        return result.data

    def _resolve_connector(self, tenant_id: str) -> str | None:
        """解析连接器。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            无结果。
        """
        if self._connector_resolver is not None:
            return self._connector_resolver(tenant_id)
        specs = self._registry.list_specs(tenant_id)
        for spec in specs:
            if spec.enabled and ("writeback" in spec.allowed_actions or not spec.allowed_actions):
                return spec.connector_id
        return None

    @staticmethod
    def _build_payload(ticket: Ticket) -> dict[str, Any]:
        """构建载荷。

        Args:
            ticket: 客服工单对象。

        Returns:
            结构化结果字典。
        """
        reply = ticket.metadata.get("reply") or {}
        draft = ticket.metadata.get("draft") or {}
        draft_text = draft.get("reply_text") if isinstance(draft, dict) else None
        return {
            "method": "POST",
            "path": "/tickets",
            "body": {
                "ticket_id": ticket.ticket_id,
                "conversation_id": ticket.conversation_id,
                "customer_id": ticket.customer_id,
                "subject": ticket.subject,
                "reply_text": reply.get("text") if isinstance(reply, dict) else None,
                "draft_text": draft_text,
                "status": ticket.status.value,
                "priority": ticket.priority.value,
                "intent": ticket.intent,
            },
        }

    async def _record_audit(
        self,
        ticket: Ticket,
        action: str,
        result: Any,
        trace_id: str,
    ) -> None:
        """记录审计。

        Args:
            ticket: 客服工单对象。
            action: 待执行动作名称。
            result: 处理结果。
            trace_id: 链路追踪 ID。
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
                actor_id="support-ticket-writeback",
                trace_id=trace_id,
                payload={
                    "ok": result.ok,
                    "error": result.error,
                    "idempotency_key": f"wb-{ticket.ticket_id}",
                },
            )
        )
