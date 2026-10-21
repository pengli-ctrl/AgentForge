"""复杂度估计与路由接线测试。"""

from agentforge.gateway.complexity import (
    ComplexityEstimate,
    RuleBasedComplexityEstimator,
    extract_features,
)
from agentforge.gateway.router import SmartRouter


def test_estimate_clamps_bounds() -> None:
    """验证分数与置信度会被限制在边界内。"""
    estimate = ComplexityEstimate(score=1.5, confidence=-0.2)
    assert estimate.score == 1.0
    assert estimate.confidence == 0.0


def test_features_are_deterministic() -> None:
    """验证同一输入会得到相同的特征。"""
    text = "请设计一个多级缓存架构\n```python\ndef f():\n    pass\n```"
    first = extract_features(text, "reasoning")
    second = extract_features(text, "reasoning")
    assert first == second
    assert first["char_length"] > 0
    assert first["code_lines"] >= 1
    assert first["keyword_hits"] >= 1


def test_rule_estimator_orders_simple_vs_complex() -> None:
    """验证复杂输入的分数高于简单输入。"""
    estimator = RuleBasedComplexityEstimator()
    simple = estimator.estimate("hello", "classification")
    complex_text = (
        "请设计并分析一个多级缓存架构,给出重构方案和 trade-off。\n"
        "```python\ndef f():\n    pass\n```"
    )
    complex_estimate = estimator.estimate(complex_text, "reasoning")
    assert 0.0 <= simple.score <= 1.0
    assert 0.0 <= complex_estimate.score <= 1.0
    assert complex_estimate.score > simple.score
    assert complex_estimate.confidence >= simple.confidence


async def test_router_uses_estimator_when_complexity_missing() -> None:
    """验证未传复杂度时会调用估计器。"""
    router = SmartRouter()
    decision = await router.route(
        "reasoning",
        input_text="请分析这个架构的取舍,并给出重构方案",
    )
    assert decision.complexity_source == "estimator"
    assert 0.0 <= decision.complexity <= 1.0
    assert decision.complexity_confidence > 0
    assert decision.complexity_features["char_length"] > 0


async def test_router_keeps_caller_complexity() -> None:
    """验证显式复杂度不会经过估计器。"""
    router = SmartRouter()
    decision = await router.route("reasoning", complexity=0.2, input_text="hello")
    assert decision.complexity_source == "caller"
    assert decision.complexity == 0.2
    assert decision.complexity_confidence == 1.0
    assert decision.complexity_features == {}


async def test_custom_estimator_can_be_injected_per_module() -> None:
    """验证业务模块可以注入自己的估计器。"""

    class FixedEstimator:
        """返回固定分数的测试估计器。"""

        def estimate(self, text: str, task_type: str) -> ComplexityEstimate:
            """返回固定分数。

            Args:
                text: 待评估文本。
                task_type: 任务类型。

            Returns:
                固定分数。
            """
            return ComplexityEstimate(
                score=0.9,
                confidence=0.8,
                features={"custom": 1.0},
                reason="fixed",
            )

    router = SmartRouter(estimator=FixedEstimator())
    decision = await router.route("classification", input_text="x")
    assert decision.complexity == 0.9
    assert decision.complexity_confidence == 0.8
    assert decision.complexity_features == {"custom": 1.0}


def test_record_outcome_collects_and_sinks() -> None:
    """验证路由结果会进入内存记录并触发回调。"""
    sink: list[dict] = []
    router = SmartRouter(outcome_sink=sink.append)
    router.record_outcome(
        task_type="reasoning",
        selected_model="Qwen3-Pro",
        success=True,
        quality=0.9,
        cost=0.01,
        complexity=0.7,
        features={"token_estimate": 100.0},
    )
    records = router.get_routing_records()
    assert len(records) == 1
    assert records[0]["selected_model"] == "Qwen3-Pro"
    assert sink[0]["quality"] == 0.9
