"""AgentForge 平台测试层：test_quality_gate。

本测试模块验证 test_quality_gate 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_prompt_registry_register_resolve_render、test_prompt_registry_publish_deprecates_previous、test_prompt_registry_missing_placeholder_raises、test_prompt_registry_unknown_raises、test_model_version_registry_resolve_and_retire、test_classification_evaluation_accuracy、test_gate_retrieval_pass、test_gate_retrieval_block_on_low_recall。
"""

import pytest

from agentforge.platform.application.classification_evaluation_service import (
    ClassificationEvaluationService,
)
from agentforge.platform.application.prompt_registry import PromptRegistry
from agentforge.platform.application.quality_gate_service import QualityGateService
from agentforge.platform.application.version_registry import ModelVersionRegistry
from agentforge.platform.domain.quality import (
    ClassificationGoldenItem,
    ClassificationReport,
    ModelVersion,
    PromptStatus,
    PromptTemplate,
    QualityGateVerdict,
    ReleaseCandidate,
)
from agentforge.platform.domain.retrieval import RetrievalReport


def _retrieval_report(**overrides):
    """执行 _retrieval_report 对应的逻辑，并返回处理结果。

    Args:
        **overrides: Any，调用方传入的 **overrides 参数。

    Returns:
        None，函数执行后的结果。
    """
    base = dict(
        query_count=2,
        recall_at_k=1.0,
        precision_at_k=0.5,
        mean_reciprocal_rank=1.0,
        citation_accuracy=1.0,
        k=5,
        per_query=[],
    )
    base.update(overrides)
    return RetrievalReport(**base)


def _classification_report(**overrides):
    """执行 _classification_report 对应的逻辑，并返回处理结果。

    Args:
        **overrides: Any，调用方传入的 **overrides 参数。

    Returns:
        None，函数执行后的结果。
    """
    base = dict(
        sample_count=2,
        classification_accuracy=1.0,
        priority_accuracy=1.0,
        risk_accuracy=1.0,
        structured_output_rate=1.0,
        high_risk_miss_rate=0.0,
        per_sample=[],
    )
    base.update(overrides)
    return ClassificationReport(**base)


# 说明：该步骤用于保证业务流程、租户隔离和可追踪性。


def test_prompt_registry_register_resolve_render() -> None:
    """验证 prompt_registry_register_resolve_render 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    registry = PromptRegistry()
    registry.register(PromptTemplate(name="reply", version="1.0", content="Answer to {question}"))
    registry.publish("reply", "1.0")
    rendered = registry.render("reply", version="1.0", question="refund")
    assert rendered == "Answer to refund"
    template = registry.resolve("reply")
    assert template.status == PromptStatus.ACTIVE


def test_prompt_registry_publish_deprecates_previous() -> None:
    """验证 prompt_registry_publish_deprecates_previous 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    registry = PromptRegistry()
    registry.register(PromptTemplate(name="reply", version="1.0", content="v1 {q}"))
    registry.register(PromptTemplate(name="reply", version="2.0", content="v2 {q}"))
    registry.publish("reply", "1.0")
    registry.publish("reply", "2.0")
    assert registry.resolve("reply").version == "2.0"
    assert registry.resolve("reply", version="1.0").status == PromptStatus.DEPRECATED


def test_prompt_registry_missing_placeholder_raises() -> None:
    """验证 prompt_registry_missing_placeholder_raises 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    registry = PromptRegistry()
    registry.register(PromptTemplate(name="t", version="1.0", content="Hi {name}"))
    with pytest.raises(ValueError):
        registry.render("t", version="1.0")  # 缺少 name


def test_prompt_registry_unknown_raises() -> None:
    """验证 prompt_registry_unknown_raises 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    registry = PromptRegistry()
    with pytest.raises(ValueError):
        registry.resolve("nope")
    assert registry.get("nope") is None


# 说明：该步骤用于保证业务流程、租户隔离和可追踪性。


def test_model_version_registry_resolve_and_retire() -> None:
    """验证 model_version_registry_resolve_and_retire 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    registry = ModelVersionRegistry()
    registry.register(
        ModelVersion(
            name="gpt", provider="litellm", model_id="gpt-4", version="1.0", capability_score=7.0
        )
    )
    registry.register(
        ModelVersion(
            name="gpt", provider="litellm", model_id="gpt-4", version="2.0", capability_score=9.0
        )
    )
    current = registry.resolve("gpt")
    assert current.version == "2.0"
    registry.retire("gpt", "2.0")
    assert registry.resolve("gpt").version == "1.0"
    assert registry.get("gpt", version="2.0").status.value == "retired"


# 说明：该步骤用于保证业务流程、租户隔离和可追踪性。


@pytest.mark.asyncio
async def test_classification_evaluation_accuracy() -> None:
    """验证 classification_evaluation_accuracy 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    from agentforge.platform.application.classifier import RuleBasedTicketClassifier

    service = ClassificationEvaluationService(RuleBasedTicketClassifier())
    samples = [
        ClassificationGoldenItem(
            tenant_id="t1",
            query="I want a refund now",
            expected_intent="complaint_or_refund",
            expected_priority="p0",
            expected_risk_level="high",
        ),
        ClassificationGoldenItem(
            tenant_id="t1",
            query="What is the price of the plan?",
            expected_intent="sales_question",
            expected_priority="p2",
            expected_risk_level="low",
        ),
        # 规则分类器无法命中此类，产生分类错误
        ClassificationGoldenItem(
            tenant_id="t1",
            query="my account cannot log in",
            expected_intent="account_issue",
            expected_priority="p1",
            expected_risk_level="low",
        ),
    ]
    report = await service.evaluate(samples)
    assert report.sample_count == 3
    assert report.classification_accuracy == pytest.approx(2 / 3)
    assert report.priority_accuracy == pytest.approx(2 / 3)
    assert report.structured_output_rate == 1.0
    assert report.high_risk_miss_rate == 0.0


# 说明：该步骤用于保证业务流程、租户隔离和可追踪性。


def test_gate_retrieval_pass() -> None:
    """验证 gate_retrieval_pass 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    service = QualityGateService()
    result = service.gate_retrieval(_retrieval_report())
    assert result.verdict == QualityGateVerdict.PASS


def test_gate_retrieval_block_on_low_recall() -> None:
    """验证 gate_retrieval_block_on_low_recall 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    service = QualityGateService()
    result = service.gate_retrieval(_retrieval_report(recall_at_k=0.2, citation_accuracy=0.3))
    assert result.verdict == QualityGateVerdict.BLOCK
    assert any("recall_at_k" in f for f in result.failed)


def test_gate_retrieval_hold_below_target() -> None:
    """验证 gate_retrieval_hold_below_target 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    service = QualityGateService()
    result = service.gate_retrieval(_retrieval_report(recall_at_k=0.7, citation_accuracy=0.75))
    assert result.verdict == QualityGateVerdict.HOLD


def test_gate_classification_block_on_high_risk_miss() -> None:
    """验证 gate_classification_block_on_high_risk_miss 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    service = QualityGateService()
    report = _classification_report(
        classification_accuracy=0.95,
        high_risk_miss_rate=0.5,
    )
    result = service.gate_classification(report)
    assert result.verdict == QualityGateVerdict.BLOCK
    assert any("high_risk_miss" in f for f in result.failed)


def test_gate_aggregate_combines_retrieval_and_classification() -> None:
    """验证 gate_aggregate_combines_retrieval_and_classification 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    service = QualityGateService()
    candidate = ReleaseCandidate(
        candidate_id="c1",
        tenant_id="t1",
        prompt_name="reply",
        prompt_version="2.0",
        model_name="gpt",
        model_version="2.0",
    )
    # classification 完全达标，但 retrieval 召回过低 → BLOCK
    result = service.gate(
        candidate,
        retrieval=_retrieval_report(recall_at_k=0.1),
        classification=_classification_report(),
    )
    assert result.verdict == QualityGateVerdict.BLOCK
    assert result.metrics["recall_at_k"] == pytest.approx(0.1)
    assert result.metrics["classification_accuracy"] == pytest.approx(1.0)


def test_gate_empty_returns_pass() -> None:
    """验证 gate_empty_returns_pass 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    service = QualityGateService()
    candidate = ReleaseCandidate(
        candidate_id="c2",
        tenant_id="t1",
        prompt_name="p",
        prompt_version="1",
        model_name="m",
        model_version="1",
    )
    result = service.gate(candidate)  # 无任何评估 → PASS
    assert result.verdict == QualityGateVerdict.PASS


# ---------- P0-5：priority / 结构化合法率 / risk 真正判级 ----------


def test_gate_classification_block_on_low_priority() -> None:
    """验证 gate_classification_block_on_low_priority 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    service = QualityGateService()
    # classification/structured/risk 达标，但 priority 低于硬底线 → 仍应 BLOCK
    report = _classification_report(
        classification_accuracy=0.95,
        priority_accuracy=0.3,
        structured_output_rate=0.95,
        risk_accuracy=0.95,
        high_risk_miss_rate=0.0,
    )
    result = service.gate_classification(report)
    assert result.verdict == QualityGateVerdict.BLOCK
    assert any("priority_accuracy" in f for f in result.failed)


def test_gate_classification_block_on_low_structured() -> None:
    """验证 gate_classification_block_on_low_structured 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    service = QualityGateService()
    # 其余达标，但结构化合法率过低 → BLOCK
    report = _classification_report(
        classification_accuracy=0.95,
        priority_accuracy=0.95,
        structured_output_rate=0.5,
        risk_accuracy=0.95,
    )
    result = service.gate_classification(report)
    assert result.verdict == QualityGateVerdict.BLOCK
    assert any("structured_output_rate" in f for f in result.failed)


def test_gate_classification_hold_on_below_target_priority() -> None:
    """验证 gate_classification_hold_on_below_target_priority 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    service = QualityGateService()
    # priority 高于硬底线但低于目标 → HOLD
    report = _classification_report(
        classification_accuracy=0.95,
        priority_accuracy=0.8,  # 说明：该步骤用于保证业务流程、租户隔离和可追踪性。
        structured_output_rate=1.0,
        risk_accuracy=0.95,
    )
    result = service.gate_classification(report)
    assert result.verdict == QualityGateVerdict.HOLD
    assert any("priority_accuracy" in w for w in result.warned)


def test_gate_classification_block_on_low_risk_accuracy() -> None:
    """验证 gate_classification_block_on_low_risk_accuracy 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    service = QualityGateService()
    report = _classification_report(
        classification_accuracy=0.95,
        priority_accuracy=0.95,
        structured_output_rate=1.0,
        risk_accuracy=0.4,  # 低于硬底线 0.75
    )
    result = service.gate_classification(report)
    assert result.verdict == QualityGateVerdict.BLOCK
    assert any("risk_accuracy" in f for f in result.failed)


def test_gate_classification_all_four_indicators_present_in_metrics() -> None:
    """验证 gate_classification_all_four_indicators_present_in_metrics 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    service = QualityGateService()
    result = service.gate_classification(_classification_report())
    for name in (
        "classification_accuracy",
        "priority_accuracy",
        "structured_output_rate",
        "risk_accuracy",
    ):
        assert result.metrics[name + "_hard"] is not None
        assert result.metrics[name + "_target"] is not None
    assert result.verdict == QualityGateVerdict.PASS
