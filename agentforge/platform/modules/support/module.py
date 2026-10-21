"""模块。"""

from __future__ import annotations

from dataclasses import dataclass

from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.priority import PriorityLevel
from agentforge.platform.modules.support.api.router import create_support_router
from agentforge.platform.modules.support.application.classifier import RuleBasedTicketClassifier
from agentforge.platform.modules.support.application.high_risk_authorizer import (
    HighRiskActionAuthorizer,
)
from agentforge.platform.modules.support.application.notification import SupportNotificationService
from agentforge.platform.modules.support.application.processing import (
    SupportTicketProcessingService,
)
from agentforge.platform.modules.support.application.reply_draft import ReplyDraftService
from agentforge.platform.modules.support.application.routing import (
    SupportSlaMetricsService,
    SupportTicketPolicy,
)
from agentforge.platform.modules.support.application.service import SupportTicketService
from agentforge.platform.modules.support.application.writeback import TicketWritebackService
from agentforge.platform.modules.support.config import SupportModuleConfig, default_support_config
from agentforge.platform.modules.support.ports import (
    NotificationPort,
    ReplyConnectorPort,
    TicketRepository,
)
from agentforge.platform.modules.support.runtime import SupportRuntime, configure_support_runtime
from agentforge.platform.modules.support.workflows.sla_sweep import (
    SupportSlaSweepWorkflow,
    sweep_support_sla_activity,
)
from agentforge.platform.modules.support.workflows.support_ticket import (
    SupportTicketWorkflow,
    apply_approval_activity,
    intake_ticket_activity,
)
from agentforge.platform.sdk.module import ModuleContext, ModuleManifest, ModuleRuntime
from agentforge.platform.sdk.ports import AuthenticatorPort


@dataclass(frozen=True)
class SupportModuleDependencies:
    """客服模块依赖相关组件。

    Attributes:
        authenticator: 认证器。
        ticket_repository: 工单仓储。
        reply_connector: 回复连接器。
        notification_gateway: 通知网关。
        webhook_secret: Webhook密钥。
    """

    authenticator: AuthenticatorPort
    ticket_repository: TicketRepository
    reply_connector: ReplyConnectorPort | None
    notification_gateway: NotificationPort | None = None
    webhook_secret: str = ""


class SupportModule:
    """客服工单模块，验证共享内核与模块契约。"""

    manifest = ModuleManifest(
        name="support",
        version="0.1.0",
        api_prefix="/v1/support",
        task_queue="support-copilot",
        migration_namespace="support",
        depends_on=(
            "core.tenant",
            "core.audit",
            "core.outbox",
            "core.connector",
            "core.cost",
            "core.identity",
            "core.knowledge",
            "core.model",
            "core.workflow",
        ),
        permissions=(
            "support.ticket.read",
            "support.ticket.review",
            "support.ticket.approve",
        ),
        enabled_by_default=True,
        config_schema=SupportModuleConfig,
        config_defaults=default_support_config().model_dump(mode="json"),
        published_events=(
            "support.ticket.sla_due_soon.v1",
            "support.ticket.sla_breached.v1",
        ),
        consumed_events=(
            "expense.invoice.gate_alert.v1",
            "expense.invoice.gate_alert_resolved.v1",
        ),
    )

    def __init__(self, dependencies: SupportModuleDependencies) -> None:
        """初始化 SupportModule。

        Args:
            dependencies: 依赖。
        """
        self._dependencies = dependencies

    def build(self, ctx: ModuleContext) -> ModuleRuntime:
        """构建客服模块。

        Args:
            ctx: 执行上下文。

        Returns:
            模块运行时结果。
        """
        dependencies = self._dependencies
        ticket_policy = SupportTicketPolicy.from_values(
            ctx.config.values,
            tenant_config=ctx.tenant_config,
        )
        classifier = RuleBasedTicketClassifier()
        ticket_service = SupportTicketService(
            dependencies.ticket_repository,
            classifier,
            dependencies.reply_connector,
            ctx.audit,
            ctx.evaluation,
            ticket_policy=ticket_policy,
        )
        sla_metrics = SupportSlaMetricsService(dependencies.ticket_repository, ticket_policy)
        notification_service = (
            SupportNotificationService(
                dependencies.notification_gateway,
                dependencies.ticket_repository,
                ctx.audit,
                usage=ctx.usage,
            )
            if dependencies.notification_gateway is not None
            else None
        )
        sweep_value = ctx.config.values.get("sla_sweep_minutes")
        sweep_minutes = float(str(sweep_value)) if sweep_value is not None else 5.0

        async def ensure_sla_sweep_schedule() -> None:
            """确保SLA扫描调度。"""
            if ctx.workflow is None or sweep_minutes <= 0:
                return
            ensure_schedule = getattr(ctx.workflow, "ensure_schedule", None)
            if not callable(ensure_schedule):
                return
            await ensure_schedule(
                SupportSlaSweepWorkflow,
                {},
                schedule_id="support-sla-sweep",
                interval_seconds=sweep_minutes * 60,
                task_queue=self.manifest.task_queue,
                workflow_id="support-sla-sweep-run",
            )

        high_risk_authorizer = HighRiskActionAuthorizer(
            ctx.policy,
            ctx.audit,
            ctx.identity,
        )
        ticket_writeback_service = TicketWritebackService(
            ctx.connectors,
            ctx.audit,
            high_risk_authorizer=high_risk_authorizer,
        )
        reply_draft_service = ReplyDraftService(ctx.models)
        processing_service = SupportTicketProcessingService(
            ticket_service,
            dependencies.ticket_repository,
            ctx.knowledge,
            reply_draft_service,
            ctx.cost,
            ctx.audit,
        )
        self._runtime = SupportRuntime(
            authenticator=dependencies.authenticator,
            module_access=ctx.module_access,
            ticket_service=ticket_service,
            repository=dependencies.ticket_repository,
            reply_connector=dependencies.reply_connector,
            notification_gateway=dependencies.notification_gateway,
            ticket_writeback_service=ticket_writeback_service,
            processing_service=processing_service,
            workflow_client=ctx.workflow,
            webhook_secret=dependencies.webhook_secret,
        )
        configure_support_runtime(self._runtime)
        router = create_support_router(
            self._runtime,
            webhook_secret=self._runtime.webhook_secret,
            prefix="",
        )
        legacy_router = create_support_router(
            self._runtime,
            webhook_secret=self._runtime.webhook_secret,
        )

        async def handle_invoice_gate_alert(event: EventEnvelope) -> None:
            """处理发票门禁告警。

            Args:
                event: 待处理事件。
            """
            tenant_policy = await ticket_policy.for_tenant(event.tenant_id)
            payload = event.payload
            alert_type = str(payload.get("type") or "invoice_gate_alert")
            message = str(payload.get("message") or "invoice gate alert")
            alert_id = str(payload.get("alert_id") or event.event_id)
            severity = str(payload.get("severity") or "warning")
            await ticket_service.create_from_event(
                {
                    "tenant_id": event.tenant_id,
                    "source": "expense-invoice-gate",
                    "message_id": alert_id,
                    "text": f"Invoice gate alert {alert_type}: {message}",
                    "routing": {
                        "assigned_team": tenant_policy.invoice_gate_team,
                        "assignee_id": tenant_policy.invoice_gate_assignee or None,
                        "queue": tenant_policy.invoice_gate_team,
                        "intent": "invoice_gate_exception",
                        "priority": _severity_priority(severity).value,
                        "sla_minutes": tenant_policy.invoice_gate_sla_minutes,
                        "sla_policy": "invoice-gate",
                    },
                    "metadata": {
                        "alert_type": alert_type,
                        "alert_id": alert_id,
                        "claim_id": payload.get("claim_id"),
                        "actor_id": payload.get("actor_id"),
                        "severity": severity,
                        "occurrence": int(payload.get("occurrence") or 1),
                        "notification_target": tenant_policy.notification_target,
                        "expense_event_id": event.event_id,
                    },
                }
            )

        async def handle_invoice_gate_alert_resolved(event: EventEnvelope) -> None:
            """处理发票门禁告警已解决。

            Args:
                event: 待处理事件。
            """
            payload = event.payload
            await ticket_service.resolve_invoice_gate_alert(
                {
                    "tenant_id": event.tenant_id,
                    "source": "expense-invoice-gate",
                    "alert_id": str(payload.get("alert_id") or event.event_id),
                    "alert_type": str(payload.get("type") or "invoice_gate_alert"),
                    "claim_id": payload.get("claim_id"),
                    "actor_id": payload.get("actor_id"),
                    "resolution": payload.get("resolution"),
                    "resolved_at": payload.get("resolved_at"),
                    "event_id": event.event_id,
                    "trace_id": event.trace_id,
                    "text": (
                        "Invoice gate alert "
                        f"{payload.get('type') or 'invoice_gate_alert'} resolved: "
                        f"{payload.get('message') or 'condition cleared'}"
                    ),
                }
            )

        async def handle_sla_notification(event: EventEnvelope) -> None:
            """处理SLA通知。

            Args:
                event: 待处理事件。
            """
            if notification_service is not None:
                await notification_service.handle_sla_event(event)

        return ModuleRuntime(
            router=router,
            legacy_routers=[legacy_router],
            temporal_workflows=[SupportTicketWorkflow, SupportSlaSweepWorkflow],
            temporal_activities=[
                intake_ticket_activity,
                apply_approval_activity,
                sweep_support_sla_activity,
            ],
            event_handlers={
                "expense.invoice.gate_alert.v1": handle_invoice_gate_alert,
                "expense.invoice.gate_alert_resolved.v1": handle_invoice_gate_alert_resolved,
                "support.ticket.sla_due_soon.v1": handle_sla_notification,
                "support.ticket.sla_breached.v1": handle_sla_notification,
            },
            metric_providers=[sla_metrics.render_metrics],
            startup_hooks=[ensure_sla_sweep_schedule],
        )


def _severity_priority(severity: str) -> PriorityLevel:
    """处理严重性优先级。

    Args:
        severity: 严重性。

    Returns:
        优先级级别结果。
    """
    if severity == "critical":
        return PriorityLevel.P0
    if severity == "high":
        return PriorityLevel.P1
    if severity == "warning":
        return PriorityLevel.P2
    return PriorityLevel.P3
