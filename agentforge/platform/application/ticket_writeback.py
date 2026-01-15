"""AgentForge 平台应用服务层：ticket_writeback。

本模块负责 ticket_writeback 相关的平台能力，是 平台应用服务层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：TicketWritebackService。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from agentforge.platform.application.connector_registry import ConnectorRegistry
from agentforge.platform.application.ports import AuditRepository
from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.authorization import AuthorizationOutcome
from agentforge.platform.domain.connector import ConnectorContext
from agentforge.platform.domain.ticket import Ticket

Resolver = Callable[[str], str | None]


class TicketWritebackService:
    """TicketWritebackService。

    TicketWritebackService 编排业务流程，协调仓储、模型、策略和外部连接器完成用例。

    主要成员：
    - 方法 write_back()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(
        self,
        registry: ConnectorRegistry,
        audit_repository: AuditRepository | None = None,
        connector_resolver: Callable[[str], str | None] | None = None,
        high_risk_authorizer=None,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            registry: ConnectorRegistry，调用方传入的 registry 参数。
            audit_repository: AuditRepository | None，调用方传入的 audit_repository 参数。
            connector_resolver: Callable[[str], str | None] | None，调用方传入的 connector_resolver 参数。
            high_risk_authorizer: Any，调用方传入的 high_risk_authorizer 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._registry = registry
        self._audit_repository = audit_repository
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        self._connector_resolver = connector_resolver
        self._high_risk_authorizer = high_risk_authorizer

    async def _check_authorization(self, ticket: Ticket, action: str, actor: str) -> None:
        """执行 _check_authorization 对应的逻辑，并返回处理结果。

        Args:
            ticket: Ticket，调用方传入的 ticket 参数。
            action: str，调用方传入的 action 参数。
            actor: str，调用方传入的 actor 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            PermissionError: 当输入、状态或外部依赖不满足要求时抛出。
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
        """执行 write_back 对应的逻辑，并返回处理结果。

        Args:
            ticket: Ticket，调用方传入的 ticket 参数。
            action: str，调用方传入的 action 参数。
            actor: str，调用方传入的 actor 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
            RuntimeError: 当输入、状态或外部依赖不满足要求时抛出。
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
        """执行 _resolve_connector 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            str | None，函数执行后的结果。
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
        """执行 _build_payload 对应的逻辑，并返回处理结果。

        Args:
            ticket: Ticket，调用方传入的 ticket 参数。

        Returns:
            dict[str, Any]，函数执行后的结果。
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
        """执行 _record_audit 对应的逻辑，并返回处理结果。

        Args:
            ticket: Ticket，调用方传入的 ticket 参数。
            action: str，调用方传入的 action 参数。
            result: Any，调用方传入的 result 参数。
            trace_id: str，调用方传入的 trace_id 参数。

        Returns:
            None，函数执行后的结果。
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
