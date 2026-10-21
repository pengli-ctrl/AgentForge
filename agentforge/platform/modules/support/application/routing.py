"""路由模块。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from agentforge.platform.domain.priority import PriorityLevel
from agentforge.platform.modules.support.config import SupportModuleConfig
from agentforge.platform.modules.support.domain.ticket import Ticket, TicketStatus
from agentforge.platform.modules.support.ports import TicketRepository
from agentforge.platform.sdk.ports import TenantConfigPort

_TERMINAL_STATUSES = {TicketStatus.PUBLISHED, TicketStatus.CANCELLED}


@dataclass(frozen=True)
class SupportIntentRoute:
    """客服路由相关组件。

    Attributes:
        assigned_team: 字段值。
        queue: 队列。
        assignee_id: 处理人ID。
        sla_minutes: SLA。
        priority: 优先级。
    """

    assigned_team: str
    queue: str = ""
    assignee_id: str = ""
    sla_minutes: int | None = None
    priority: PriorityLevel | None = None


@dataclass(frozen=True)
class SupportTicketPolicy:
    """客服工单策略领域组件。

    Attributes:
        default_sla_minutes: 默认SLA。
        invoice_gate_team: 发票门禁。
        invoice_gate_assignee: 发票门禁。
        sla_escalation_assignee: SLA升级。
        invoice_gate_sla_minutes: 发票门禁SLA。
        due_soon_seconds: 到期。
        default_team: 默认。
        default_queue: 默认队列。
        notification_target: 通知目标。
        intent_routes: 路由。
        tenant_config: 租户配置。
    """

    default_sla_minutes: int = 480
    invoice_gate_team: str = "finance-invoice-gate"
    invoice_gate_assignee: str = ""
    sla_escalation_assignee: str = ""
    invoice_gate_sla_minutes: int = 60
    due_soon_seconds: int = 900
    default_team: str = "support"
    default_queue: str = ""
    notification_target: str = ""
    intent_routes: Mapping[str, SupportIntentRoute] = field(default_factory=dict)
    tenant_config: TenantConfigPort | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        """校验并补全初始化后的字段。"""
        object.__setattr__(self, "default_sla_minutes", max(1, self.default_sla_minutes))
        object.__setattr__(
            self,
            "invoice_gate_sla_minutes",
            max(1, self.invoice_gate_sla_minutes),
        )
        object.__setattr__(self, "due_soon_seconds", max(0, self.due_soon_seconds))
        object.__setattr__(
            self,
            "invoice_gate_team",
            self.invoice_gate_team.strip() or "finance-invoice-gate",
        )
        object.__setattr__(self, "invoice_gate_assignee", self.invoice_gate_assignee.strip())
        object.__setattr__(self, "sla_escalation_assignee", self.sla_escalation_assignee.strip())
        object.__setattr__(self, "default_team", self.default_team.strip() or "support")
        object.__setattr__(self, "default_queue", self.default_queue.strip())
        object.__setattr__(self, "notification_target", self.notification_target.strip())

    @classmethod
    def from_values(
        cls,
        values: Mapping[str, Any],
        *,
        tenant_config: TenantConfigPort | None = None,
    ) -> "SupportTicketPolicy":
        """从值构造当前对象。

        Args:
            values: 字段值集合。
            tenant_config: 租户配置。

        Returns:
            工单结果。
        """
        config = SupportModuleConfig.model_validate(dict(values))
        routes = {
            intent: SupportIntentRoute(
                assigned_team=route.assigned_team,
                queue=route.queue,
                assignee_id=route.assignee_id,
                sla_minutes=route.sla_minutes,
                priority=(PriorityLevel(route.priority) if route.priority is not None else None),
            )
            for intent, route in config.intent_routes.items()
        }
        return cls(
            default_sla_minutes=config.default_sla_minutes,
            invoice_gate_team=config.invoice_gate_team,
            invoice_gate_assignee=config.invoice_gate_assignee,
            sla_escalation_assignee=config.sla_escalation_assignee,
            invoice_gate_sla_minutes=config.invoice_gate_sla_minutes,
            due_soon_seconds=config.sla_due_soon_seconds,
            default_team=config.default_team,
            default_queue=config.default_queue,
            notification_target=config.notification_target,
            intent_routes=routes,
            tenant_config=tenant_config,
        )

    async def for_tenant(self, tenant_id: str) -> "SupportTicketPolicy":
        """加载指定租户的客服策略。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            工单结果。
        """
        if self.tenant_config is None:
            return self
        values = await self.tenant_config.effective_values(tenant_id)
        return self.from_values(values)

    def apply(
        self,
        ticket: Ticket,
        *,
        source: str,
        routing: Mapping[str, Any] | None = None,
    ) -> None:
        """应用客服工单策略。

        Args:
            ticket: 客服工单对象。
            source: 调用或事件来源。
            routing: 输入参数。
        """
        overrides = dict(routing or {})
        if source == "expense-invoice-gate" and not overrides:
            overrides.update(
                {
                    "assigned_team": self.invoice_gate_team,
                    "assignee_id": self.invoice_gate_assignee or None,
                    "intent": "invoice_gate_exception",
                    "sla_minutes": self.invoice_gate_sla_minutes,
                }
            )

        intent = str(overrides.get("intent") or ticket.intent or "general_question")
        intent_route = self.intent_routes.get(intent)
        assigned_team = str(
            overrides.get("assigned_team")
            or (intent_route.assigned_team if intent_route is not None else "")
            or ticket.assigned_team
            or self.default_team
        )
        fallback_priority = (
            intent_route.priority
            if intent_route is not None and intent_route.priority is not None
            else ticket.priority
        )
        priority = self._priority(overrides.get("priority"), fallback_priority)
        assignee_id = (
            str(
                overrides.get("assignee_id")
                or (intent_route.assignee_id if intent_route is not None else "")
                or ticket.assignee_id
                or ""
            ).strip()
            or None
        )
        queue = str(
            overrides.get("queue")
            or (intent_route.queue if intent_route is not None else "")
            or self.default_queue
            or assigned_team
        )
        route_sla = intent_route.sla_minutes if intent_route is not None else None
        sla_minutes = self._positive_int(
            overrides.get("sla_minutes"),
            route_sla or self._priority_minutes(priority),
        )

        ticket.assigned_team = assigned_team
        ticket.assignee_id = assignee_id
        ticket.intent = intent
        ticket.priority = priority
        ticket.metadata["queue"] = queue
        ticket.metadata["notification_target"] = self.notification_target
        ticket.metadata["routing"] = {
            "source": source,
            "assigned_team": assigned_team,
            "queue": queue,
            "assignee_id": assignee_id,
            "priority": priority.value,
            "overridden": bool(overrides),
            "intent_route": intent in self.intent_routes,
        }
        due_at = _as_utc(ticket.created_at) + timedelta(minutes=sla_minutes)
        ticket.metadata["sla"] = {
            "policy": str(overrides.get("sla_policy") or f"{source}:{priority.value}"),
            "minutes": sla_minutes,
            "due_at": due_at.isoformat(),
            "status": "open",
        }

    @staticmethod
    def close_sla(ticket: Ticket, *, outcome: str, closed_at: datetime | None = None) -> None:
        """关闭SLA。

        Args:
            ticket: 客服工单对象。
            outcome: 输入参数。
            closed_at: 已关闭时间。
        """
        sla = ticket.metadata.get("sla")
        if not isinstance(sla, dict) or sla.get("status") != "open":
            return
        timestamp = closed_at or datetime.now(timezone.utc)
        due_at = parse_datetime(sla.get("due_at"))
        if outcome == "cancelled":
            status = "cancelled"
        elif due_at is not None and timestamp > due_at:
            status = "breached"
        else:
            status = "met"
        sla["status"] = status
        sla["closed_at"] = timestamp.isoformat()
        ticket.metadata["sla"] = sla

    def _priority_minutes(self, priority: PriorityLevel) -> int:
        """处理优先级。

        Args:
            priority: 优先级。

        Returns:
            整数结果。
        """
        if priority == PriorityLevel.P0:
            return min(30, self.default_sla_minutes)
        if priority == PriorityLevel.P1:
            return min(60, self.default_sla_minutes)
        if priority == PriorityLevel.P2:
            return min(240, self.default_sla_minutes)
        return self.default_sla_minutes

    @staticmethod
    def _priority(value: object, fallback: PriorityLevel) -> PriorityLevel:
        """处理优先级。

        Args:
            value: 待处理值。
            fallback: 输入参数。

        Returns:
            优先级级别结果。
        """
        if isinstance(value, PriorityLevel):
            return value
        if isinstance(value, str):
            try:
                return PriorityLevel(value.lower())
            except ValueError:
                return fallback
        return fallback

    @staticmethod
    def _positive_int(value: object, fallback: int) -> int:
        """处理整数。

        Args:
            value: 待处理值。
            fallback: 输入参数。

        Returns:
            整数结果。
        """
        try:
            parsed = int(str(value))
        except (TypeError, ValueError):
            return fallback
        return parsed if parsed > 0 else fallback


class SupportSlaMetricsService:
    """客服SLA指标应用服务，编排领域用例及其副作用。"""

    def __init__(self, repository: TicketRepository, policy: SupportTicketPolicy) -> None:
        """初始化 SupportSlaMetricsService。

        Args:
            repository: 数据仓储实现。
            policy: 策略定义。
        """
        self._repository = repository
        self._policy = policy

    async def render_metrics(self) -> str:
        """渲染指标。

        Returns:
            字符串结果。
        """
        tickets = await self._repository.list_all(limit=10_000)
        now = datetime.now(timezone.utc)
        open_counts: dict[tuple[str, str, str], int] = {}
        overdue_counts: dict[tuple[str, str, str], int] = {}
        due_soon_counts: dict[tuple[str, str, str], int] = {}
        oldest_age: dict[tuple[str, str], float] = {}
        tenant_policies: dict[str, SupportTicketPolicy] = {}

        for ticket in tickets:
            if ticket.status in _TERMINAL_STATUSES:
                continue
            sla = ticket.metadata.get("sla")
            if not isinstance(sla, dict):
                continue
            due_at = parse_datetime(sla.get("due_at"))
            if due_at is None:
                continue
            policy = tenant_policies.get(ticket.tenant_id)
            if policy is None:
                policy = await self._policy.for_tenant(ticket.tenant_id)
                tenant_policies[ticket.tenant_id] = policy
            team = ticket.assigned_team or "support"
            priority = ticket.priority.value
            key = (ticket.tenant_id, team, priority)
            open_counts[key] = open_counts.get(key, 0) + 1
            remaining = (due_at - now).total_seconds()
            if remaining < 0:
                overdue_counts[key] = overdue_counts.get(key, 0) + 1
            elif remaining <= policy.due_soon_seconds:
                due_soon_counts[key] = due_soon_counts.get(key, 0) + 1
            team_key = (ticket.tenant_id, team)
            created_at = _as_utc(ticket.created_at)
            age_seconds = max(0.0, (now - created_at).total_seconds())
            oldest_age[team_key] = max(oldest_age.get(team_key, 0.0), age_seconds)

        lines = [
            "# HELP agentforge_support_ticket_sla_open Open tickets with an SLA.",
            "# TYPE agentforge_support_ticket_sla_open gauge",
        ]
        for (tenant_id, team, priority), open_value in sorted(open_counts.items()):
            lines.append(
                "agentforge_support_ticket_sla_open"
                f'{{tenant_id="{_label(tenant_id)}",team="{_label(team)}",'
                f'priority="{_label(priority)}"}} {open_value}'
            )
        lines.extend(
            [
                "# HELP agentforge_support_ticket_sla_overdue Open tickets past their SLA.",
                "# TYPE agentforge_support_ticket_sla_overdue gauge",
            ]
        )
        for (tenant_id, team, priority), overdue_value in sorted(overdue_counts.items()):
            lines.append(
                "agentforge_support_ticket_sla_overdue"
                f'{{tenant_id="{_label(tenant_id)}",team="{_label(team)}",'
                f'priority="{_label(priority)}"}} {overdue_value}'
            )
        lines.extend(
            [
                "# HELP agentforge_support_ticket_sla_due_soon Tickets approaching their SLA.",
                "# TYPE agentforge_support_ticket_sla_due_soon gauge",
            ]
        )
        for (tenant_id, team, priority), due_soon_value in sorted(due_soon_counts.items()):
            lines.append(
                "agentforge_support_ticket_sla_due_soon"
                f'{{tenant_id="{_label(tenant_id)}",team="{_label(team)}",'
                f'priority="{_label(priority)}"}} {due_soon_value}'
            )
        lines.extend(
            [
                "# HELP agentforge_support_ticket_sla_oldest_open_age_seconds "
                "Oldest open ticket age by team.",
                "# TYPE agentforge_support_ticket_sla_oldest_open_age_seconds gauge",
            ]
        )
        for (tenant_id, team), oldest_value in sorted(oldest_age.items()):
            lines.append(
                "agentforge_support_ticket_sla_oldest_open_age_seconds"
                f'{{tenant_id="{_label(tenant_id)}",team="{_label(team)}"}} {oldest_value:.3f}'
            )
        return "\n".join(lines) + "\n"


def _as_utc(value: datetime) -> datetime:
    """处理作为UTC。

    Args:
        value: 待处理值。

    Returns:
        处理结果对象。
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def parse_datetime(value: object) -> datetime | None:
    """解析请求。

    Args:
        value: 待处理值。

    Returns:
        无结果。
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _label(value: str) -> str:
    """处理标签。

    Args:
        value: 待处理值。

    Returns:
        字符串结果。
    """
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
