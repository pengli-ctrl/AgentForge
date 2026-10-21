"""分类评估服务模块。"""

from __future__ import annotations

from agentforge.platform.domain.classification import StructuredClassifier
from agentforge.platform.domain.quality import (
    ClassificationEvaluation,
    ClassificationGoldenItem,
    ClassificationReport,
)


def _average(values: list[float]) -> float:
    """计算指标平均值。

    Args:
        values: 字段值集合。

    Returns:
        数值结果。
    """
    if not values:
        return 0.0
    return sum(values) / len(values)


class ClassificationEvaluationService:
    """分类评估应用服务，编排领域用例及其副作用。"""

    def __init__(self, classifier: StructuredClassifier) -> None:
        """初始化 ClassificationEvaluationService。

        Args:
            classifier: 分类器。
        """
        self._classifier = classifier

    async def evaluate(self, samples: list[ClassificationGoldenItem]) -> ClassificationReport:
        """评估输入数据并生成结果。

        Args:
            samples: 样本。

        Returns:
            分类报告结果。
        """
        evaluations: list[ClassificationEvaluation] = []
        for item in samples:
            model = await self._classifier.classify_structured(item.query)
            result = model.result
            predicted_intent = result.intent
            predicted_priority = result.priority.value
            predicted_risk = result.risk_level.value

            # 高风险漏报：样本标定高/关键风险，但预测为低/中。
            expected_high = item.expected_risk_level in {"high", "critical"}
            predicted_low = result.risk_level in {"low", "medium"}
            high_risk_missed = bool(expected_high and predicted_low)

            evaluations.append(
                ClassificationEvaluation(
                    query=item.query,
                    predicted_intent=predicted_intent,
                    predicted_priority=predicted_priority,
                    predicted_risk_level=predicted_risk,
                    structured_valid=result.structured_valid if item.expect_structured else True,
                    intent_correct=predicted_intent == item.expected_intent,
                    priority_correct=predicted_priority == item.expected_priority,
                    risk_correct=predicted_risk == item.expected_risk_level,
                    high_risk_missed=high_risk_missed,
                    confidence=result.confidence,
                )
            )

        n = len(evaluations)
        return ClassificationReport(
            sample_count=n,
            classification_accuracy=_average([e.intent_correct for e in evaluations]),
            priority_accuracy=_average([e.priority_correct for e in evaluations]),
            risk_accuracy=_average([e.risk_correct for e in evaluations]),
            structured_output_rate=_average([e.structured_valid for e in evaluations]),
            high_risk_miss_rate=_average([e.high_risk_missed for e in evaluations]),
            per_sample=evaluations,
        )
