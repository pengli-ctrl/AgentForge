"""客服处理测试模块。

本测试模块验证 test_support_processing 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：BadCitationGateway。
-
主要函数：test_processing_service_creates_cited_draft、test_processing_service_escalates_without_knowl
    edge、test_processing_service_rejects_invalid_citations。
"""

import pytest

from agentforge.platform.domain.model import ModelResponse
from agentforge.platform.modules.support.domain.ticket import TicketStatus
from agentforge.platform.runtime import build_memory_container
from tests.platform.support_fixtures import configure_memory_support


@pytest.mark.asyncio
async def test_processing_service_creates_cited_draft() -> None:
    """验证处理服务创建引用草稿对应的测试场景。"""
    container = build_memory_container()
    support = configure_memory_support(container)
    await container.knowledge_service.ingest_document(
        tenant_id="tenant-1",
        title="Product usage",
        content="How to use this product: open the dashboard and follow the setup guide.",
    )
    ticket = await support.processing_service.process_event(
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
    """验证处理服务升级不包含知识对应的测试场景。"""
    container = build_memory_container()
    support = configure_memory_support(container)
    ticket = await support.processing_service.process_event(
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
    """异常引用网关抽象。"""

    async def complete(self, request):
        """完成异常引用。

        Args:
            request: 当前 HTTP 请求。

        Returns:
            处理结果。
        """
        return ModelResponse(
            content="Unsupported answer",
            model="bad-model",
            provider="test",
            citations=["not-a-valid-chunk"],
        )


@pytest.mark.asyncio
async def test_processing_service_rejects_invalid_citations() -> None:
    """验证处理服务拒绝无效引用对应的测试场景。"""
    container = build_memory_container(model_gateway=BadCitationGateway())
    support = configure_memory_support(container)
    await container.knowledge_service.ingest_document(
        tenant_id="tenant-1",
        title="Refund policy",
        content="Refunds are available within seven days for product issues.",
    )
    ticket = await support.processing_service.process_event(
        {
            "tenant_id": "tenant-1",
            "source": "feishu",
            "message_id": "process-msg-3",
            "text": "How do I use this product?",
        }
    )
    assert ticket.status == TicketStatus.WAITING_APPROVAL
    assert ticket.metadata["draft"]["citations"] == []
