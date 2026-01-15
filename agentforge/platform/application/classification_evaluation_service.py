"""AgentForge 平台应用服务层：classification_evaluation_service。

本模块实现 classification_evaluation_service 应用服务，编排多个领域对象和基础设施组件完成业务流程。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：ClassificationEvaluationService。
"""

from __future__ import annotations

from agentforge.platform.application.classifier import StructuredClassifier
from agentforge.platform.domain.quality import (
    ClassificationEvaluation,
    ClassificationGoldenItem,
    ClassificationReport,
)


def _average(values: list[float]) -> float:
    """执行 _average 对应的逻辑，并返回处理结果。

    Args:
        values: list[float]，调用方传入的 values 参数。

    Returns:
        float，函数执行后的结果。
    """
    if not values:
        return 0.0
    return sum(values) / len(values)


class ClassificationEvaluationService:
    """ClassificationEvaluationService。

    ClassificationEvaluationService 编排业务流程，协调仓储、模型、策略和外部连接器完成用例。

    主要成员：
    - 方法 evaluate()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self, classifier: StructuredClassifier) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            classifier: StructuredClassifier，调用方传入的 classifier 参数。

        Returns:
            None，函数执行后的结果。
        """
        self._classifier = classifier

    async def evaluate(self, samples: list[ClassificationGoldenItem]) -> ClassificationReport:
        """执行 evaluate 对应的逻辑，并返回处理结果。

        Args:
            samples: list[ClassificationGoldenItem]，调用方传入的 samples 参数。

        Returns:
            ClassificationReport，函数执行后的结果。
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
