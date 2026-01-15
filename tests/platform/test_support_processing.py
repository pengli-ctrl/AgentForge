"""AgentForge 平台测试层：test_support_processing。

本测试模块验证 test_support_processing 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：BadCitationGateway。
-
主要函数：test_processing_service_creates_cited_draft、test_processing_service_escalates_without_knowledge、test_processing_service_rejects_invalid_citations。
"""

import pytest

from agentforge.platform.domain.model import ModelResponse
from agentforge.platform.domain.ticket import TicketStatus
from agentforge.platform.runtime import build_memory_container


@pytest.mark.asyncio
async def test_processing_service_creates_cited_draft() -> None:
    """验证 processing_service_creates_cited_draft 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
    """验证 processing_service_escalates_without_knowledge 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
    """BadCitationGateway。

    BadCitationGateway 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

    主要成员：
    - 方法 complete()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    async def complete(self, request):
        """执行 complete 对应的逻辑，并返回处理结果。

        Args:
            request: Any，调用方传入的 request 参数。

        Returns:
            None，函数执行后的结果。
        """
        return ModelResponse(
            content="Unsupported answer",
            model="bad-model",
            provider="test",
            citations=["not-a-valid-chunk"],
        )


@pytest.mark.asyncio
async def test_processing_service_rejects_invalid_citations() -> None:
    """验证 processing_service_rejects_invalid_citations 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
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
