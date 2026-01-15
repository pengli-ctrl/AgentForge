"""AgentForge 平台应用服务层：ports。

本模块负责 ports 相关的平台能力，是 平台应用服务层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要类：TicketRepository、KnowledgeRepository、CostRepository、EventPublisher、ModelGateway、VectorStore、ReplyConnector、AuditRepository。
"""

from __future__ import annotations

import builtins
from datetime import datetime
from typing import Protocol

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.connector import ConnectorSpec
from agentforge.platform.domain.cost import CostRecord
from agentforge.platform.domain.evaluation import EvaluationSample
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.knowledge import (
    KnowledgeChunk,
    KnowledgeDocument,
    RetrievedChunk,
    SearchMode,
)
from agentforge.platform.domain.model import ModelRequest, ModelResponse
from agentforge.platform.domain.rbac import Role, RoleAssignment
from agentforge.platform.domain.regression import GoldenItem, QualityReport, RegressionRun
from agentforge.platform.domain.reporting import ReportRun, ScheduledReport
from agentforge.platform.domain.tenant_quota import TenantQuota
from agentforge.platform.domain.ticket import Ticket


class TicketRepository(Protocol):
    """TicketRepository。

    TicketRepository 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 get()。
    - 方法 save()。
    - 方法 get_by_idempotency_key()。
    - 方法 list()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def get(self, tenant_id: str, ticket_id: str) -> Ticket | None:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            ticket_id: str，调用方传入的 ticket_id 参数。

        Returns:
            Ticket | None，函数执行后的结果。
        """
        ...

    async def save(
        self,
        ticket: Ticket,
        events: list[EventEnvelope] | None = None,
    ) -> Ticket:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            ticket: Ticket，调用方传入的 ticket 参数。
            events: list[EventEnvelope] | None，调用方传入的 events 参数。

        Returns:
            Ticket，函数执行后的结果。
        """
        ...

    async def get_by_idempotency_key(self, tenant_id: str, idempotency_key: str) -> Ticket | None:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            idempotency_key: str，调用方传入的 idempotency_key 参数。

        Returns:
            Ticket | None，函数执行后的结果。
        """
        ...

    async def list(
        self,
        tenant_id: str,
        status: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[Ticket], str | None]:
        """执行 list 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            status: str | None，调用方传入的 status 参数。
            limit: int，调用方传入的 limit 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            tuple[list[Ticket], str | None]，函数执行后的结果。
        """
        ...


class KnowledgeRepository(Protocol):
    """KnowledgeRepository。

    KnowledgeRepository 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 save_document()。
    - 方法 search()。
    - 方法 backfill_embeddings()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def save_document(
        self,
        document: KnowledgeDocument,
        chunks: list[KnowledgeChunk],
    ) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            document: KnowledgeDocument，调用方传入的 document 参数。
            chunks: list[KnowledgeChunk]，调用方传入的 chunks 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...

    async def search(
        self,
        tenant_id: str,
        query: str,
        limit: int = 5,
        mode: SearchMode = "hybrid",
        fts_weight: float = 0.5,
        vector_weight: float = 0.5,
    ) -> list[RetrievedChunk]:
        """执行 search 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            query: str，调用方传入的 query 参数。
            limit: int，调用方传入的 limit 参数。
            mode: SearchMode，调用方传入的 mode 参数。
            fts_weight: float，调用方传入的 fts_weight 参数。
            vector_weight: float，调用方传入的 vector_weight 参数。

        Returns:
            list[RetrievedChunk]，函数执行后的结果。
        """
        ...

    async def backfill_embeddings(self, tenant_id: str | None = None) -> int:
        """回填缺失数据，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。

        Returns:
            int，函数执行后的结果。
        """
        ...


class CostRepository(Protocol):
    """CostRepository。

    CostRepository 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 save()。
    - 方法 total_for_tenant()。
    - 方法 monthly_total_for_tenant()。
    - 方法 summary_for_tenant()。
    - 方法 list_tenants()。
    - 方法 daily_summary()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def save(self, record: CostRecord) -> None:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            record: CostRecord，调用方传入的 record 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...

    async def total_for_tenant(self, tenant_id: str) -> float:
        """执行 total_for_tenant 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            float，函数执行后的结果。
        """
        ...

    async def monthly_total_for_tenant(self, tenant_id: str, now: datetime) -> float:
        """执行 monthly_total_for_tenant 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            now: datetime，调用方传入的 now 参数。

        Returns:
            float，函数执行后的结果。
        """
        ...

    async def summary_for_tenant(self, tenant_id: str) -> dict:
        """执行 summary_for_tenant 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。
        """
        ...

    async def list_tenants(self) -> list[str]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Returns:
            list[str]，函数执行后的结果。
        """
        ...

    async def daily_summary(
        self,
        tenant_id: str,
        days: int = 30,
    ) -> list[dict]:
        """执行 daily_summary 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            days: int，调用方传入的 days 参数。

        Returns:
            list[dict]，函数执行后的结果。
        """
        ...


class EventPublisher(Protocol):
    """EventPublisher。

    EventPublisher 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 publish()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def publish(self, event: EventEnvelope) -> None:
        """执行 publish 对应的核心操作，并保持调用契约稳定。

        Args:
            event: EventEnvelope，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...


class ModelGateway(Protocol):
    """ModelGateway。

    ModelGateway 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 complete()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """执行 complete 对应的逻辑，并返回处理结果。

        Args:
            request: ModelRequest，调用方传入的 request 参数。

        Returns:
            ModelResponse，函数执行后的结果。
        """
        ...


class VectorStore(Protocol):
    """VectorStore。

    VectorStore 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 search()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def search(self, tenant_id: str, query: str, limit: int = 5) -> list[dict]:
        """执行 search 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            query: str，调用方传入的 query 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[dict]，函数执行后的结果。
        """
        ...


class ReplyConnector(Protocol):
    """ReplyConnector。

    ReplyConnector 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 send_text()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def send_text(
        self,
        target: str,
        text: str,
        idempotency_key: str,
    ) -> dict:
        """执行 send_text 对应的逻辑，并返回处理结果。

        Args:
            target: str，调用方传入的 target 参数。
            text: str，调用方传入的 text 参数。
            idempotency_key: str，调用方传入的 idempotency_key 参数。

        Returns:
            dict，函数执行后的结果。
        """
        ...


class AuditRepository(Protocol):
    """AuditRepository。

    AuditRepository 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 save()。
    - 方法 list_events()。
    - 方法 query_events()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def save(self, event: AuditEvent) -> None:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            event: AuditEvent，调用方传入的 event 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...

    async def list_events(
        self,
        tenant_id: str,
        limit: int = 100,
        resource_id: str | None = None,
    ) -> list[AuditEvent]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。
            resource_id: str | None，调用方传入的 resource_id 参数。

        Returns:
            list[AuditEvent]，函数执行后的结果。
        """
        ...

    async def query_events(
        self,
        tenant_id: str | None = None,
        action: str | None = None,
        actor_id: str | None = None,
        resource_id: str | None = None,
        resource_type: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[AuditEvent], str | None]:
        """执行查询并返回结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            action: str | None，调用方传入的 action 参数。
            actor_id: str | None，调用方传入的 actor_id 参数。
            resource_id: str | None，调用方传入的 resource_id 参数。
            resource_type: str | None，调用方传入的 resource_type 参数。
            limit: int，调用方传入的 limit 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            tuple[list[AuditEvent], str | None]，函数执行后的结果。
        """
        ...


class EvaluationRepository(Protocol):
    """EvaluationRepository。

    EvaluationRepository 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 save()。
    - 方法 list_samples()。
    - 方法 summary()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def save(self, sample: EvaluationSample) -> None:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            sample: EvaluationSample，调用方传入的 sample 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...

    async def list_samples(
        self,
        tenant_id: str,
        limit: int = 100,
        action: str | None = None,
    ) -> list[EvaluationSample]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。
            action: str | None，调用方传入的 action 参数。

        Returns:
            list[EvaluationSample]，函数执行后的结果。
        """
        ...

    async def summary(self, tenant_id: str) -> dict:
        """执行 summary 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            dict，函数执行后的结果。
        """
        ...


class RegressionRepository(Protocol):
    """RegressionRepository。

    RegressionRepository 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 save_golden()。
    - 方法 list_golden()。
    - 方法 save_run()。
    - 方法 save_report()。
    - 方法 get_run()。
    - 方法 list_runs()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def save_golden(self, item: GoldenItem) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            item: GoldenItem，调用方传入的 item 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...

    async def list_golden(
        self,
        tenant_id: str,
        limit: int = 100,
    ) -> list[GoldenItem]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[GoldenItem]，函数执行后的结果。
        """
        ...

    async def save_run(self, run: RegressionRun) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            run: RegressionRun，调用方传入的 run 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...

    async def save_report(self, report: QualityReport) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            report: QualityReport，调用方传入的 report 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...

    async def get_run(self, run_id: str) -> RegressionRun | None:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            run_id: str，调用方传入的 run_id 参数。

        Returns:
            RegressionRun | None，函数执行后的结果。
        """
        ...

    async def list_runs(self, tenant_id: str, limit: int = 100) -> list[RegressionRun]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[RegressionRun]，函数执行后的结果。
        """
        ...


class ConnectorRepository(Protocol):
    """ConnectorRepository。

    ConnectorRepository 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 save_spec()。
    - 方法 get_spec()。
    - 方法 list_specs()。
    - 方法 delete_spec()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def save_spec(self, spec: ConnectorSpec) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            spec: ConnectorSpec，调用方传入的 spec 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...

    async def get_spec(self, connector_id: str) -> ConnectorSpec | None:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            connector_id: str，调用方传入的 connector_id 参数。

        Returns:
            ConnectorSpec | None，函数执行后的结果。
        """
        ...

    async def list_specs(
        self,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[ConnectorSpec]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[ConnectorSpec]，函数执行后的结果。
        """
        ...

    async def delete_spec(self, connector_id: str) -> None:
        """删除指定数据，并返回调用方需要的结果。

        Args:
            connector_id: str，调用方传入的 connector_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...


class RbacRepository(Protocol):
    """RbacRepository。

    RbacRepository 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 save_role()。
    - 方法 get_role()。
    - 方法 list_roles()。
    - 方法 save_assignment()。
    - 方法 list_assignments()。
    - 方法 assignments_for_user()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def save_role(self, role: Role) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            role: Role，调用方传入的 role 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...

    async def get_role(self, tenant_id: str, role_id: str) -> Role | None:
        """读取并返回指定数据，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            role_id: str，调用方传入的 role_id 参数。

        Returns:
            Role | None，函数执行后的结果。
        """
        ...

    async def list_roles(self, tenant_id: str) -> list[Role]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            list[Role]，函数执行后的结果。
        """
        ...

    async def save_assignment(self, assignment: RoleAssignment) -> None:
        """保存业务数据，并返回调用方需要的结果。

        Args:
            assignment: RoleAssignment，调用方传入的 assignment 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...

    async def list_assignments(self, tenant_id: str) -> list[RoleAssignment]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            list[RoleAssignment]，函数执行后的结果。
        """
        ...

    async def assignments_for_user(
        self,
        tenant_id: str,
        user_id: str,
    ) -> list[RoleAssignment]:
        """执行 assignments_for_user 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            user_id: str，调用方传入的 user_id 参数。

        Returns:
            list[RoleAssignment]，函数执行后的结果。
        """
        ...


class TenantQuotaRepository(Protocol):
    """TenantQuotaRepository。

    TenantQuotaRepository 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 upsert()。
    - 方法 get()。
    - 方法 list()。
    - 方法 delete()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def upsert(self, quota: TenantQuota) -> None:
        """执行 upsert 对应的逻辑，并返回处理结果。

        Args:
            quota: TenantQuota，调用方传入的 quota 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...

    async def get(self, tenant_id: str) -> TenantQuota | None:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            TenantQuota | None，函数执行后的结果。
        """
        ...

    async def list(self, limit: int = 100) -> list[TenantQuota]:
        """执行 list 对应的核心操作，并保持调用契约稳定。

        Args:
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[TenantQuota]，函数执行后的结果。
        """
        ...

    async def delete(self, tenant_id: str) -> None:
        """执行 delete 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...


class ScheduledReportRepository(Protocol):
    """ScheduledReportRepository。

    ScheduledReportRepository 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 save()。
    - 方法 get()。
    - 方法 list_schedules()。
    - 方法 delete()。
    - 方法 list_due()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def save(self, report: ScheduledReport) -> None:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            report: ScheduledReport，调用方传入的 report 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...

    async def get(self, report_id: str) -> ScheduledReport | None:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            report_id: str，调用方传入的 report_id 参数。

        Returns:
            ScheduledReport | None，函数执行后的结果。
        """
        ...

    async def list_schedules(
        self, tenant_id: str | None = None, limit: int = 100
    ) -> list[ScheduledReport]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[ScheduledReport]，函数执行后的结果。
        """
        ...

    async def delete(self, report_id: str) -> None:
        """执行 delete 对应的核心操作，并保持调用契约稳定。

        Args:
            report_id: str，调用方传入的 report_id 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...

    async def list_due(
        self,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[ScheduledReport]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            before: datetime | None，调用方传入的 before 参数。
            limit: int，调用方传入的 limit 参数。

        Returns:
            list[ScheduledReport]，函数执行后的结果。
        """
        ...


class ReportRunRepository(Protocol):
    """ReportRunRepository。

    ReportRunRepository 定义依赖倒置接口，隔离应用层与具体基础设施实现。

    主要成员：
    - 方法 save()。
    - 方法 get()。
    - 方法 list()。
    - 方法 list_page()。
    - 方法 set_archived()。
    - 方法 delete_older_than()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def save(self, run: ReportRun) -> None:
        """执行 save 对应的核心操作，并保持调用契约稳定。

        Args:
            run: ReportRun，调用方传入的 run 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...

    async def get(self, run_id: str) -> ReportRun | None:
        """执行 get 对应的核心操作，并保持调用契约稳定。

        Args:
            run_id: str，调用方传入的 run_id 参数。

        Returns:
            ReportRun | None，函数执行后的结果。
        """
        ...

    async def list(
        self,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
        archived: bool | None = None,
    ) -> list[ReportRun]:
        """执行 list 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            report_type: str | None，调用方传入的 report_type 参数。
            limit: int，调用方传入的 limit 参数。
            archived: bool | None，调用方传入的 archived 参数。

        Returns:
            list[ReportRun]，函数执行后的结果。
        """
        ...

    async def list_page(
        self,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
        archived: bool | None = None,
        cursor: str | None = None,
    ) -> tuple[builtins.list[ReportRun], str | None]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            report_type: str | None，调用方传入的 report_type 参数。
            limit: int，调用方传入的 limit 参数。
            archived: bool | None，调用方传入的 archived 参数。
            cursor: str | None，调用方传入的 cursor 参数。

        Returns:
            tuple[builtins.list[ReportRun], str | None]，函数执行后的结果。
        """
        ...

    async def set_archived(self, run_id: str, archived: bool) -> None:
        """执行 set_archived 对应的逻辑，并返回处理结果。

        Args:
            run_id: str，调用方传入的 run_id 参数。
            archived: bool，调用方传入的 archived 参数。

        Returns:
            None，函数执行后的结果。
        """
        ...

    async def delete_older_than(
        self,
        cutoff: datetime,
        tenant_id: str | None = None,
        include_archived: bool = False,
    ) -> int:
        """删除指定数据，并返回调用方需要的结果。

        Args:
            cutoff: datetime，调用方传入的 cutoff 参数。
            tenant_id: str | None，调用方传入的 tenant_id 参数。
            include_archived: bool，调用方传入的 include_archived 参数。

        Returns:
            int，函数执行后的结果。
        """
        ...
