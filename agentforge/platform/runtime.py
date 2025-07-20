from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.api.security import ApiKeyAuthenticator
from agentforge.platform.application.classifier import RuleBasedTicketClassifier
from agentforge.platform.application.knowledge_service import KnowledgeService
from agentforge.platform.application.model_router import ModelRouter
from agentforge.platform.application.quota_service import QuotaAwareModelGateway
from agentforge.platform.application.reply_draft_service import ReplyDraftService
from agentforge.platform.application.routing_model_gateway import RoutingModelGateway
from agentforge.platform.application.support_ticket_processing_service import (
    SupportTicketProcessingService,
)
from agentforge.platform.application.support_ticket_service import SupportTicketService
from agentforge.platform.domain.model import ModelProfile
from agentforge.platform.infrastructure.llm.litellm_gateway import LiteLLMModelGateway
from agentforge.platform.infrastructure.llm.static_gateway import StaticModelGateway
from agentforge.platform.infrastructure.memory_audit_repository import MemoryAuditRepository
from agentforge.platform.infrastructure.memory_cost_repository import MemoryCostRepository
from agentforge.platform.infrastructure.memory_evaluation_repository import (
    MemoryEvaluationRepository,
)
from agentforge.platform.infrastructure.memory_knowledge_repository import MemoryKnowledgeRepository
from agentforge.platform.infrastructure.memory_reply_connector import MemoryReplyConnector
from agentforge.platform.infrastructure.memory_ticket_repository import MemoryTicketRepository
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore
from agentforge.platform.infrastructure.sqlalchemy_audit_repository import SQLAlchemyAuditRepository
from agentforge.platform.infrastructure.sqlalchemy_cost_repository import SQLAlchemyCostRepository
from agentforge.platform.infrastructure.sqlalchemy_evaluation_repository import (
    SQLAlchemyEvaluationRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_knowledge_repository import (
    SQLAlchemyKnowledgeRepository,
)
from agentforge.platform.infrastructure.sqlalchemy_ticket_repository import (
    SQLAlchemyTicketRepository,
)
from agentforge.platform.settings import get_settings

DEFAULT_PROFILES = [
    ModelProfile(
        name="fast-local",
        provider="local",
        model_id="static-local",
        capability_score=5.0,
        cost_per_1k_tokens=0.001,
        avg_latency_ms=500,
        task_types=["classification", "general"],
    ),
    ModelProfile(
        name="balanced-cloud",
        provider="litellm",
        model_id="gpt-4.1-mini",
        capability_score=8.0,
        cost_per_1k_tokens=0.01,
        avg_latency_ms=1800,
        task_types=["drafting", "general"],
    ),
]


class ServiceContainer:
    def __init__(
        self,
        repository,
        classifier,
        knowledge_repository,
        model_gateway,
        cost_repository,
        outbox_store=None,
        workflow_client=None,
        reply_connector=None,
        audit_repository=None,
        authenticator: ApiKeyAuthenticator | None = None,
        evaluation_repository=None,
    ) -> None:
        self.repository = repository
        self.classifier = classifier
        self.knowledge_repository = knowledge_repository
        self.model_gateway = model_gateway
        self.cost_repository = cost_repository
        self.outbox_store = outbox_store
        self.workflow_client = workflow_client
        self.reply_connector = reply_connector
        self.audit_repository = audit_repository
        self.authenticator = authenticator or ApiKeyAuthenticator(enabled=False)
        self.evaluation_repository = evaluation_repository
        self.ticket_service = SupportTicketService(
            repository,
            classifier,
            reply_connector,
            audit_repository,
            evaluation_repository,
        )
        self.knowledge_service = KnowledgeService(knowledge_repository)
        self.reply_draft_service = ReplyDraftService(model_gateway)
        self.processing_service = SupportTicketProcessingService(
            self.ticket_service,
            repository,
            self.knowledge_service,
            self.reply_draft_service,
            cost_repository,
            audit_repository,
        )


_default_container: ServiceContainer | None = None


def _wrap_gateway(inner, cost_repository) -> QuotaAwareModelGateway:
    router = ModelRouter(DEFAULT_PROFILES)
    routed = RoutingModelGateway(router, inner)
    budget = get_settings().monthly_model_budget
    return QuotaAwareModelGateway(routed, cost_repository, budget)


def build_memory_container(
    model_gateway=None,
    authenticator: ApiKeyAuthenticator | None = None,
) -> ServiceContainer:
    cost_repository = MemoryCostRepository()
    audit_repository = MemoryAuditRepository()
    evaluation_repository = MemoryEvaluationRepository()
    reply_connector = MemoryReplyConnector()
    return ServiceContainer(
        MemoryTicketRepository(),
        RuleBasedTicketClassifier(),
        MemoryKnowledgeRepository(),
        _wrap_gateway(model_gateway or StaticModelGateway(), cost_repository),
        cost_repository,
        reply_connector=reply_connector,
        audit_repository=audit_repository,
        authenticator=authenticator,
        evaluation_repository=evaluation_repository,
    )


def build_sqlalchemy_container(
    session_factory: async_sessionmaker[AsyncSession],
    model_gateway=None,
    workflow_client=None,
    reply_connector=None,
    authenticator: ApiKeyAuthenticator | None = None,
) -> ServiceContainer:
    cost_repository = SQLAlchemyCostRepository(session_factory)
    audit_repository = SQLAlchemyAuditRepository(session_factory)
    evaluation_repository = SQLAlchemyEvaluationRepository(session_factory)
    return ServiceContainer(
        SQLAlchemyTicketRepository(session_factory),
        RuleBasedTicketClassifier(),
        SQLAlchemyKnowledgeRepository(session_factory),
        _wrap_gateway(model_gateway or LiteLLMModelGateway(), cost_repository),
        cost_repository,
        SQLAlchemyOutboxStore(session_factory),
        workflow_client,
        reply_connector,
        audit_repository,
        authenticator,
        evaluation_repository,
    )


def configure_container(container: ServiceContainer) -> None:
    global _default_container
    _default_container = container


def get_container() -> ServiceContainer:
    global _default_container
    if _default_container is None:
        _default_container = build_memory_container()
    return _default_container
