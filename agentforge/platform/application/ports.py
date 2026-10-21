"""端口模块。"""

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
from agentforge.platform.domain.upload import UploadSession


class KnowledgeRepository(Protocol):
    """知识仓储，负责持久化读写。"""

    async def save_document(
        self,
        document: KnowledgeDocument,
        chunks: list[KnowledgeChunk],
    ) -> None:
        """保存文档。

        Args:
            document: 文档。
            chunks: 文本分片列表。
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
        """搜索知识。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            query: 检索或筛选查询。
            limit: 返回记录的最大数量。
            mode: 运行模式。
            fts_weight: 输入参数。
            vector_weight: 输入参数。

        Returns:
            结果列表。
        """
        ...

    async def backfill_embeddings(self, tenant_id: str | None = None) -> int:
        """回填向量。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            整数结果。
        """
        ...


class UploadSessionRepository(Protocol):
    """上传会话仓储，负责持久化读写。"""

    async def save(self, session: UploadSession) -> None:
        """保存上传会话。

        Args:
            session: 当前会话。
        """
        ...

    async def get(self, tenant_id: str, upload_id: str) -> UploadSession | None:
        """读取上传会话。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            upload_id: 上传会话 ID。

        Returns:
            上传会话无结果。
        """
        ...


class CostRepository(Protocol):
    """成本仓储，负责持久化读写。"""

    async def save(self, record: CostRecord) -> None:
        """保存成本。

        Args:
            record: 待处理的领域记录。
        """
        ...

    async def total_for_tenant(self, tenant_id: str) -> float:
        """获取租户的总计。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            数值结果。
        """
        ...

    async def monthly_total_for_tenant(self, tenant_id: str, now: datetime) -> float:
        """获取租户的月度总计。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            now: 输入参数。

        Returns:
            数值结果。
        """
        ...

    async def summary_for_tenant(self, tenant_id: str) -> dict:
        """获取租户的摘要。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        ...

    async def list_tenants(self) -> list[str]:
        """查询租户。

        Returns:
            结果列表。
        """
        ...

    async def daily_summary(
        self,
        tenant_id: str,
        days: int = 30,
    ) -> list[dict]:
        """生成每日摘要。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            days: 统计天数。

        Returns:
            结果列表。
        """
        ...


class EventPublisher(Protocol):
    """事件发布器。"""

    async def publish(self, event: EventEnvelope) -> None:
        """发布事件发布器。

        Args:
            event: 待处理事件。
        """
        ...


class ModelGateway(Protocol):
    """模型能力端口协议。"""

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """完成模型。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            模型响应结果。
        """
        ...


class VectorStore(Protocol):
    """向量存储能力端口。"""

    async def search(self, tenant_id: str, query: str, limit: int = 5) -> list[dict]:
        """搜索与查询条件匹配的数据。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            query: 检索或筛选查询。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...


class ReplyConnector(Protocol):
    """回复连接器实现。"""

    async def send_text(
        self,
        target: str,
        text: str,
        idempotency_key: str,
    ) -> dict:
        """发送文本。

        Args:
            target: 操作目标。
            text: 待处理文本。
            idempotency_key: 幂等键，用于避免重复处理。

        Returns:
            结构化结果字典。
        """
        ...


class AuditRepository(Protocol):
    """审计仓储，负责持久化读写。"""

    async def save(self, event: AuditEvent) -> None:
        """保存审计。

        Args:
            event: 待处理事件。
        """
        ...

    async def list_events(
        self,
        tenant_id: str,
        limit: int = 100,
        resource_id: str | None = None,
    ) -> list[AuditEvent]:
        """查询事件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。
            resource_id: 资源 ID。

        Returns:
            结果列表。
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
        """查询事件。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            action: 待执行动作名称。
            actor_id: 执行操作的参与者 ID。
            resource_id: 资源 ID。
            resource_type: 资源类型。
            limit: 返回记录的最大数量。
            cursor: 分页游标。

        Returns:
            结果元组。
        """
        ...


class EvaluationRepository(Protocol):
    """评估仓储，负责持久化读写。"""

    async def save(self, sample: EvaluationSample) -> None:
        """保存评估。

        Args:
            sample: 评估样本。
        """
        ...

    async def list_samples(
        self,
        tenant_id: str,
        limit: int = 100,
        action: str | None = None,
    ) -> list[EvaluationSample]:
        """查询样本。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。
            action: 待执行动作名称。

        Returns:
            结果列表。
        """
        ...

    async def summary(self, tenant_id: str) -> dict:
        """处理摘要。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        ...


class RegressionRepository(Protocol):
    """回归仓储，负责持久化读写。"""

    async def save_golden(self, item: GoldenItem) -> None:
        """保存基准。

        Args:
            item: 条目。
        """
        ...

    async def list_golden(
        self,
        tenant_id: str,
        limit: int = 100,
    ) -> list[GoldenItem]:
        """查询基准。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...

    async def save_run(self, run: RegressionRun) -> None:
        """保存运行。

        Args:
            run: 运行。
        """
        ...

    async def save_report(self, report: QualityReport) -> None:
        """保存报告。

        Args:
            report: 报告。
        """
        ...

    async def get_run(self, run_id: str) -> RegressionRun | None:
        """获取运行。

        Args:
            run_id: 运行记录 ID。

        Returns:
            回归运行无结果。
        """
        ...

    async def list_runs(self, tenant_id: str, limit: int = 100) -> list[RegressionRun]:
        """查询运行记录。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...


class ConnectorRepository(Protocol):
    """连接器仓储，负责持久化读写。"""

    async def save_spec(self, spec: ConnectorSpec) -> None:
        """保存规格。

        Args:
            spec: 资源规格定义。
        """
        ...

    async def get_spec(self, connector_id: str) -> ConnectorSpec | None:
        """获取规格。

        Args:
            connector_id: 连接器 ID。

        Returns:
            连接器规格无结果。
        """
        ...

    async def list_specs(
        self,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[ConnectorSpec]:
        """查询规格。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...

    async def delete_spec(self, connector_id: str) -> None:
        """删除规格。

        Args:
            connector_id: 连接器 ID。
        """
        ...


class RbacRepository(Protocol):
    """RBAC仓储，负责持久化读写。"""

    async def save_role(self, role: Role) -> None:
        """保存角色。

        Args:
            role: 角色。
        """
        ...

    async def get_role(self, tenant_id: str, role_id: str) -> Role | None:
        """读取角色。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            role_id: 角色 ID。

        Returns:
            角色无结果。
        """
        ...

    async def list_roles(self, tenant_id: str) -> list[Role]:
        """查询角色。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        ...

    async def save_assignment(self, assignment: RoleAssignment) -> None:
        """保存分配。

        Args:
            assignment: 分配。
        """
        ...

    async def list_assignments(self, tenant_id: str) -> list[RoleAssignment]:
        """查询分配记录。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        ...

    async def assignments_for_user(
        self,
        tenant_id: str,
        user_id: str,
    ) -> list[RoleAssignment]:
        """获取用户的分配记录。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            user_id: 用户 ID。

        Returns:
            结果列表。
        """
        ...


class TenantQuotaRepository(Protocol):
    """租户配额仓储，负责持久化读写。"""

    async def upsert(self, quota: TenantQuota) -> None:
        """新建或更新租户配额。

        Args:
            quota: 配额配置。
        """
        ...

    async def get(self, tenant_id: str) -> TenantQuota | None:
        """读取租户配额。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            租户配额无结果。
        """
        ...

    async def list(self, limit: int = 100) -> list[TenantQuota]:
        """查询租户配额。

        Args:
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...

    async def delete(self, tenant_id: str) -> None:
        """删除租户配额。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
        """
        ...


class ScheduledReportRepository(Protocol):
    """报告仓储，负责持久化读写。"""

    async def save(self, report: ScheduledReport) -> None:
        """保存报告。

        Args:
            report: 报告。
        """
        ...

    async def get(self, report_id: str) -> ScheduledReport | None:
        """获取报告。

        Args:
            report_id: 报告 ID。

        Returns:
            报告无结果。
        """
        ...

    async def list_schedules(
        self, tenant_id: str | None = None, limit: int = 100
    ) -> list[ScheduledReport]:
        """查询调度。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...

    async def delete(self, report_id: str) -> None:
        """删除报告。

        Args:
            report_id: 报告 ID。
        """
        ...

    async def list_due(
        self,
        before: datetime | None = None,
        limit: int = 100,
    ) -> list[ScheduledReport]:
        """查询到期。

        Args:
            before: 之前。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        ...


class ReportRunRepository(Protocol):
    """报告运行仓储，负责持久化读写。"""

    async def save(self, run: ReportRun) -> None:
        """保存报告运行。

        Args:
            run: 运行。
        """
        ...

    async def get(self, run_id: str) -> ReportRun | None:
        """获取报告运行。

        Args:
            run_id: 运行记录 ID。

        Returns:
            报告运行无结果。
        """
        ...

    async def list(
        self,
        tenant_id: str | None = None,
        report_type: str | None = None,
        limit: int = 100,
        archived: bool | None = None,
    ) -> list[ReportRun]:
        """查询报告运行。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            report_type: 报告类型。
            limit: 返回记录的最大数量。
            archived: 已归档。

        Returns:
            结果列表。
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
        """查询页面。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            report_type: 报告类型。
            limit: 返回记录的最大数量。
            archived: 已归档。
            cursor: 分页游标。

        Returns:
            结果元组。
        """
        ...

    async def set_archived(self, run_id: str, archived: bool) -> None:
        """设置已归档。

        Args:
            run_id: 运行记录 ID。
            archived: 已归档。
        """
        ...

    async def delete_older_than(
        self,
        cutoff: datetime,
        tenant_id: str | None = None,
        include_archived: bool = False,
    ) -> int:
        """删除更旧比。

        Args:
            cutoff: 截止时间。
            tenant_id: 租户 ID，用于数据隔离。
            include_archived: 已归档。

        Returns:
            整数结果。
        """
        ...
