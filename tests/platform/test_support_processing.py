import pytest

from agentforge.platform.domain.model import ModelResponse
from agentforge.platform.domain.ticket import TicketStatus
from agentforge.platform.runtime import build_memory_container


@pytest.mark.asyncio
async def test_processing_service_creates_cited_draft() -> None:
    container = build_memory_container()
    await container.knowledge_service.ingest_document(
        tenant_id="tenant-1",
        title="Product usage",
        content="How to use this product: open the dashboard and follow the setup guide.",
    )
    ticket = await container.processing_service.process_event(
        {
            "tenant_id": "tenant-1",
            "source": "feishu",
            "message_id": "process-msg-1",
            "text": "How do I use this product?",
        }
    )
    assert ticket.status == TicketStatus.WAITING_REVIEW
    assert ticket.metadata["draft"]["citations"]
    assert len(container.cost_repository.records) == 1


@pytest.mark.asyncio
async def test_processing_service_escalates_without_knowledge() -> None:
    container = build_memory_container()
    ticket = await container.processing_service.process_event(
        {
            "tenant_id": "tenant-1",
            "source": "feishu",
            "message_id": "process-msg-2",
            "text": "How do I use this product?",
        }
    )
    assert ticket.status == TicketStatus.WAITING_APPROVAL
    assert ticket.metadata["draft"]["requires_approval"] is True


class BadCitationGateway:
    async def complete(self, request):
        return ModelResponse(
            content="Unsupported answer",
            model="bad-model",
            provider="test",
            citations=["not-a-valid-chunk"],
        )


@pytest.mark.asyncio
async def test_processing_service_rejects_invalid_citations() -> None:
    container = build_memory_container(model_gateway=BadCitationGateway())
    await container.knowledge_service.ingest_document(
        tenant_id="tenant-1",
        title="Refund policy",
        content="Refunds are available within seven days for product issues.",
    )
    ticket = await container.processing_service.process_event(
        {
            "tenant_id": "tenant-1",
            "source": "feishu",
            "message_id": "process-msg-3",
            "text": "How do I use this product?",
        }
    )
    assert ticket.status == TicketStatus.WAITING_APPROVAL
    assert ticket.metadata["draft"]["citations"] == []
