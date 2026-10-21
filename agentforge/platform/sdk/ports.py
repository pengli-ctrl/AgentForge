"""端口模块。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.audit import AuditEvent
from agentforge.platform.domain.authorization import AuthorizationDecision
from agentforge.platform.domain.connector import (
    ConnectorContext,
    ConnectorInvocationResult,
    ConnectorSpec,
)
from agentforge.platform.domain.cost import CostRecord
from agentforge.platform.domain.evaluation import EvaluationSample
from agentforge.platform.domain.events import EventEnvelope
from agentforge.platform.domain.knowledge import KnowledgeDocument, RetrievedChunk, SearchMode
from agentforge.platform.domain.model import ModelRequest, ModelResponse
from agentforge.platform.domain.ocr import OcrResult
from agentforge.platform.domain.rbac import Role, RoleAssignment
from agentforge.platform.domain.upload import UploadCompletion, UploadSession
from agentforge.platform.domain.usage import UsageMetric


class AuthenticatorPort(Protocol):
    """认证器能力端口协议。"""

    def authorize_tenant(self, request: object, tenant_id: str) -> None:
        """校验请求是否允许访问租户。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
        """
        ...


class WorkflowClientPort(Protocol):
    """工作流客户端能力端口协议。"""

    async def start_workflow(
        self,
        workflow: Any,
        arg: Any,
        *,
        workflow_id: str | None = None,
        id_prefix: str = "workflow",
        task_queue: str | None = None,
    ) -> str:
        """执行开始工作流。

        Args:
            workflow: 工作流定义或实例。
            arg: 输入参数。
            workflow_id: 工作流 ID。
            id_prefix: ID前缀。
            task_queue: 任务队列。

        Returns:
            字符串结果。
        """
        ...

    async def signal_workflow(self, workflow_id: str, signal: Any, arg: Any = None) -> None:
        """通知工作流。

        Args:
            workflow_id: 工作流 ID。
            signal: 信号。
            arg: 输入参数。
        """
        ...

    async def ensure_schedule(
        self,
        workflow: Any,
        arg: Any,
        *,
        schedule_id: str,
        interval_seconds: float,
        task_queue: str | None = None,
        workflow_id: str | None = None,
    ) -> str:
        """确保调度。

        Args:
            workflow: 工作流定义或实例。
            arg: 输入参数。
            schedule_id: 调度 ID。
            interval_seconds: 输入参数。
            task_queue: 任务队列。
            workflow_id: 工作流 ID。

        Returns:
            字符串结果。
        """
        ...


class AuditPort(Protocol):
    """审计写入端口。"""

    async def save(self, event: AuditEvent) -> None:
        """持久化一条审计事件。

        Args:
            event: 待处理事件。
        """
        ...


class OutboxPort(Protocol):
    """可靠事件写入端口。"""

    async def enqueue(self, event: EventEnvelope) -> None:
        """写入队列Outbox。

        Args:
            event: 待处理事件。
        """
        ...


class UsagePort(Protocol):
    """用量能力端口协议。"""

    async def record(
        self,
        *,
        tenant_id: str,
        metric: UsageMetric,
        quantity: int,
        source: str,
        idempotency_key: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """记录用量。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            metric: 用量指标。
            quantity: 本次记录的用量数量。
            source: 调用或事件来源。
            idempotency_key: 幂等键，用于避免重复处理。
            metadata: 附加元数据。
        """
        ...


class AuthorizationPort(Protocol):
    """授权能力端口协议。"""

    async def authorize(
        self,
        *,
        tenant_id: str,
        principal: str,
        action: str,
        resource_type: str,
        resource_id: str,
        relation: str | None = None,
    ) -> AuthorizationDecision:
        """执行授权决策。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            principal: 当前认证主体。
            action: 待执行动作名称。
            resource_type: 资源类型。
            resource_id: 资源 ID。
            relation: 关系。

        Returns:
            决策结果。
        """
        ...


class ConnectorPort(Protocol):
    """外部系统连接器端口。"""

    async def invoke(
        self,
        connector_id: str,
        action: str,
        payload: dict[str, object],
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        """调用已注册的连接器动作。

        Args:
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            payload: 事件、工作流或请求载荷。
            context: 执行上下文。

        Returns:
            连接器结果结果。
        """
        ...

    async def compensate(
        self,
        connector_id: str,
        action: str,
        payload: dict[str, object],
        context: ConnectorContext,
    ) -> ConnectorInvocationResult:
        """补偿连接器。

        Args:
            connector_id: 连接器 ID。
            action: 待执行动作名称。
            payload: 事件、工作流或请求载荷。
            context: 执行上下文。

        Returns:
            连接器结果结果。
        """
        ...


class ConnectorCatalogPort(ConnectorPort, Protocol):
    """供业务模块查询可用连接器的扩展端口。"""

    def list_specs(self, tenant_id: str | None = None) -> list[ConnectorSpec]:
        """列出指定租户可用的连接器定义。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        ...


class KnowledgePort(Protocol):
    """知识库与检索端口。"""

    async def ingest_document(
        self,
        tenant_id: str,
        title: str,
        content: str,
        source_uri: str = "",
        metadata: Mapping[str, object] | None = None,
    ) -> KnowledgeDocument:
        """写入可检索文档。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            title: 输入参数。
            content: 写入内容。
            source_uri: 来源URI。
            metadata: 附加元数据。

        Returns:
            知识文档结果。
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
        rerank: bool = False,
    ) -> list[RetrievedChunk]:
        """按租户执行知识检索。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            query: 检索或筛选查询。
            limit: 返回记录的最大数量。
            mode: 运行模式。
            fts_weight: 输入参数。
            vector_weight: 输入参数。
            rerank: 重排。

        Returns:
            结果列表。
        """
        ...


class EvaluationPort(Protocol):
    """评估样本写入端口。"""

    async def save(self, sample: EvaluationSample) -> None:
        """保存人工复核评估样本。

        Args:
            sample: 评估样本。
        """
        ...


class CostPort(Protocol):
    """模型成本写入端口。"""

    async def save(self, record: CostRecord) -> None:
        """保存一条成本记录。

        Args:
            record: 待处理的领域记录。
        """
        ...


class ModelGatewayPort(Protocol):
    """统一模型调用端口。"""

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """执行一次模型调用。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            模型响应结果。
        """
        ...


class PolicyOutcomePort(Protocol):
    """策略判定结果的稳定最小视图。"""

    @property
    def value(self) -> str:
        """返回判定结果字符串。

        Returns:
            字符串结果。
        """
        ...


class PolicyDecisionPort(Protocol):
    """策略引擎返回给模块的最小判定结果。

    Attributes:
        outcome: 结果。
        reasons: 字段值。
        risk_level: 风险级别。
    """

    outcome: PolicyOutcomePort
    reasons: Sequence[str]
    risk_level: str


class PolicyPort(Protocol):
    """权限与策略判断端口。"""

    async def authorize(
        self,
        *,
        tenant_id: str,
        principal: str,
        action: str,
        roles: set[str],
        permissions: set[str],
        resource_type: str,
        resource_id: str,
        relation: str | None = None,
    ) -> PolicyDecisionPort:
        """判断主体是否允许对资源执行动作。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            principal: 当前认证主体。
            action: 待执行动作名称。
            roles: 角色。
            permissions: 权限。
            resource_type: 资源类型。
            resource_id: 资源 ID。
            relation: 关系。

        Returns:
            策略决策结果。
        """
        ...


class RbacPort(Protocol):
    """模块鉴权所需的角色与授权查询端口。"""

    async def get_role(self, tenant_id: str, role_id: str) -> Role | None:
        """按租户读取角色。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            role_id: 角色 ID。

        Returns:
            角色无结果。
        """
        ...

    async def assignments_for_user(self, tenant_id: str, principal: str) -> list[RoleAssignment]:
        """读取主体在当前租户下的角色分配。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            principal: 当前认证主体。

        Returns:
            结果列表。
        """
        ...


class ModuleAccessPort(Protocol):
    """模块访问能力端口协议。"""

    async def is_enabled(self, tenant_id: str, module_name: str) -> bool:
        """判断启用是否成立。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            module_name: 模块名称。

        Returns:
            操作是否成功。
        """
        ...


class TenantConfigPort(Protocol):
    """租户能力端口协议。"""

    async def effective_values(self, tenant_id: str) -> Mapping[str, Any]:
        """处理值。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        ...


class OcrPort(Protocol):
    """OCR能力端口协议。"""

    async def extract(self, content: bytes, content_type: str = "") -> OcrResult:
        """提取OCR。

        Args:
            content: 写入内容。
            content_type: 内容 MIME 类型。

        Returns:
            OCR结果结果。
        """
        ...


class PersistencePort(Protocol):
    """模块仓储使用的数据库会话工厂。"""

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """返回会话工厂。

        Returns:
            异步结果。
        """
        ...

    def session_factory_for(self, module_name: str) -> async_sessionmaker[AsyncSession]:
        """处理会话工厂用于。

        Args:
            module_name: 模块名称。

        Returns:
            异步结果。
        """
        ...


class ObjectStorePort(Protocol):
    """对象存储端口，用于保存原始文件和大型附件。"""

    async def put(self, key: str, data: bytes, content_type: str = "") -> None:
        """写入缓存或对象存储数据。

        Args:
            key: 缓存或配置键。
            data: 待处理数据。
            content_type: 内容 MIME 类型。
        """
        ...

    async def get(self, key: str) -> bytes:
        """读取对象。

        Args:
            key: 缓存或配置键。

        Returns:
            二进制数据。
        """
        ...

    async def presigned_get_url(self, key: str, expires_seconds: int = 300) -> str:
        """生成短时下载 URL。

        Args:
            key: 缓存或配置键。
            expires_seconds: 输入参数。

        Returns:
            字符串结果。
        """
        ...

    async def delete(self, key: str) -> None:
        """删除对象。

        Args:
            key: 缓存或配置键。
        """
        ...


class ChunkedUploadPort(Protocol):
    """上传能力端口协议。"""

    async def begin(
        self,
        *,
        tenant_id: str,
        owner_module: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        chunk_size: int,
        sha256: str | None = None,
    ) -> UploadSession:
        """开始上传。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            owner_module: 模块。
            filename: 输入参数。
            content_type: 内容 MIME 类型。
            size_bytes: 大小。
            chunk_size: 分块大小。
            sha256: 输入参数。

        Returns:
            上传会话结果。
        """
        ...

    async def get(self, tenant_id: str, upload_id: str) -> UploadSession:
        """获取上传。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            upload_id: 上传会话 ID。

        Returns:
            二进制数据。
        """
        ...

    async def put_part(
        self,
        tenant_id: str,
        upload_id: str,
        part_number: int,
        data: bytes,
        sha256: str | None = None,
    ) -> UploadSession:
        """写入分片。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            upload_id: 上传会话 ID。
            part_number: 分片。
            data: 待处理数据。
            sha256: 输入参数。

        Returns:
            上传会话结果。
        """
        ...

    async def complete(self, tenant_id: str, upload_id: str) -> UploadCompletion:
        """完成上传。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            upload_id: 上传会话 ID。

        Returns:
            上传完成结果。
        """
        ...
