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


# ---------- Prompt Registry ----------


def test_prompt_registry_register_resolve_render() -> None:
    registry = PromptRegistry()
    registry.register(PromptTemplate(name="reply", version="1.0", content="Answer to {question}"))
    registry.publish("reply", "1.0")
    rendered = registry.render("reply", version="1.0", question="refund")
    assert rendered == "Answer to refund"
    template = registry.resolve("reply")
    assert template.status == PromptStatus.ACTIVE


def test_prompt_registry_publish_deprecates_previous() -> None:
    registry = PromptRegistry()
    registry.register(PromptTemplate(name="reply", version="1.0", content="v1 {q}"))
    registry.register(PromptTemplate(name="reply", version="2.0", content="v2 {q}"))
    registry.publish("reply", "1.0")
    registry.publish("reply", "2.0")
    assert registry.resolve("reply").version == "2.0"
    assert registry.resolve("reply", version="1.0").status == PromptStatus.DEPRECATED


def test_prompt_registry_missing_placeholder_raises() -> None:
    registry = PromptRegistry()
    registry.register(PromptTemplate(name="t", version="1.0", content="Hi {name}"))
    with pytest.raises(ValueError):
        registry.render("t", version="1.0")  # 缺少 name


def test_prompt_registry_unknown_raises() -> None:
    registry = PromptRegistry()
    with pytest.raises(ValueError):
        registry.resolve("nope")
    assert registry.get("nope") is None


# ---------- Model Version Registry ----------


def test_model_version_registry_resolve_and_retire() -> None:
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


# ---------- Classification Evaluation ----------


@pytest.mark.asyncio
async def test_classification_evaluation_accuracy() -> None:
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


# ---------- Quality Gate ----------


def test_gate_retrieval_pass() -> None:
    service = QualityGateService()
    result = service.gate_retrieval(_retrieval_report())
    assert result.verdict == QualityGateVerdict.PASS


def test_gate_retrieval_block_on_low_recall() -> None:
    service = QualityGateService()
    result = service.gate_retrieval(_retrieval_report(recall_at_k=0.2, citation_accuracy=0.3))
    assert result.verdict == QualityGateVerdict.BLOCK
    assert any("recall_at_k" in f for f in result.failed)


def test_gate_retrieval_hold_below_target() -> None:
    service = QualityGateService()
    result = service.gate_retrieval(_retrieval_report(recall_at_k=0.7, citation_accuracy=0.75))
    assert result.verdict == QualityGateVerdict.HOLD


def test_gate_classification_block_on_high_risk_miss() -> None:
    service = QualityGateService()
    report = _classification_report(
        classification_accuracy=0.95,
        high_risk_miss_rate=0.5,
    )
    result = service.gate_classification(report)
    assert result.verdict == QualityGateVerdict.BLOCK
    assert any("high_risk_miss" in f for f in result.failed)


def test_gate_aggregate_combines_retrieval_and_classification() -> None:
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
