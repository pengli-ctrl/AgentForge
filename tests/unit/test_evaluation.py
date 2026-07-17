"""RAGEvaluator 单元测试 — RAGAS 评估框架。

测试要点：评估流程、LLM-as-Judge 降级、综合分数计算、Golden Dataset 处理。
"""

from __future__ import annotations

import json

import pytest

from agentforge.llm.gateway import LLMResponse
from agentforge.rag.evaluation import (
    DIMENSION_WEIGHTS,
    EvaluationResult,
    GoldenSample,
    LLMAsJudge,
    RAGEvaluator,
)
from tests.conftest import MockLLMGateway


class MockRAGPipeline:
    """Mock RAG 管道 — 返回预设检索结果和生成回答。"""

    def __init__(
        self,
        retrieved: list[str] | None = None,
        answer: str = "Generated answer",
    ) -> None:
        self._retrieved = retrieved or ["context chunk 1", "context chunk 2"]
        self._answer = answer

    def retrieve(self, query: str, top_k: int = 5) -> list[str]:
        return self._retrieved[:top_k]

    def generate(self, query: str, contexts: list[str]) -> str:
        return self._answer


class TestGoldenSample:
    """GoldenSample 数据类测试。"""

    def test_create_sample(self) -> None:
        sample = GoldenSample(
            query="What is validate_input?",
            ground_truth_context="def validate_input(data): return bool(data)",
            ground_truth_answer="validate_input checks if data is truthy",
        )
        assert sample.query == "What is validate_input?"
        assert "validate_input" in sample.ground_truth_context
        assert "validate_input" in sample.ground_truth_answer


class TestEvaluationResult:
    """EvaluationResult 数据类测试。"""

    def test_defaults(self) -> None:
        result = EvaluationResult()
        assert result.faithfulness == 0.0
        assert result.answer_relevancy == 0.0
        assert result.context_precision == 0.0
        assert result.context_recall == 0.0
        assert result.overall_score == 0.0
        assert result.sample_count == 0

    def test_to_dict(self) -> None:
        result = EvaluationResult(
            faithfulness=0.85,
            answer_relevancy=0.90,
            context_precision=0.80,
            context_recall=0.75,
            overall_score=0.835,
            sample_count=10,
        )
        d = result.to_dict()
        assert d["faithfulness"] == 0.85
        assert d["answer_relevancy"] == 0.90
        assert d["context_precision"] == 0.80
        assert d["context_recall"] == 0.75
        assert d["overall_score"] == 0.835
        assert d["sample_count"] == 10


class TestRAGEvaluatorInit:
    """RAGEvaluator 初始化测试。"""

    def test_init_with_llm(self) -> None:
        llm = MockLLMGateway()
        evaluator = RAGEvaluator(llm_gateway=llm)
        assert evaluator.llm_gateway is llm
        assert evaluator._judge is not None

    def test_has_llm_judge(self) -> None:
        llm = MockLLMGateway()
        evaluator = RAGEvaluator(llm_gateway=llm)
        assert isinstance(evaluator._judge, LLMAsJudge)


class TestEvaluate:
    """evaluate 方法测试。"""

    def test_evaluate_empty_dataset(self) -> None:
        llm = MockLLMGateway()
        evaluator = RAGEvaluator(llm_gateway=llm)
        result = evaluator.evaluate([], MockRAGPipeline())
        assert result["sample_count"] == 0
        assert result["overall_score"] == 0.0

    def test_evaluate_with_golden_samples(self) -> None:
        """评估应返回包含四个维度分数的结果。"""
        # Mock LLM 返回评分 JSON
        judge_response = json.dumps({"score": 0.8, "reason": "good match"})
        llm = MockLLMGateway(
            responses=[
                LLMResponse(content=judge_response),  # faithfulness
                LLMResponse(content=judge_response),  # answer_relevancy
                LLMResponse(content=judge_response),  # context_precision
                LLMResponse(content=judge_response),  # context_recall
            ]
        )
        evaluator = RAGEvaluator(llm_gateway=llm)

        samples = [
            GoldenSample(
                query="What does validate_input do?",
                ground_truth_context="def validate_input(data): return bool(data)",
                ground_truth_answer="It checks if data is truthy",
            ),
        ]

        pipeline = MockRAGPipeline(
            retrieved=["def validate_input(data): return bool(data)"],
            answer="validate_input checks if data is truthy",
        )

        result = evaluator.evaluate(samples, pipeline)

        assert result["sample_count"] == 1
        assert "faithfulness" in result
        assert "answer_relevancy" in result
        assert "context_precision" in result
        assert "context_recall" in result
        assert "overall_score" in result

    def test_evaluate_with_dict_samples(self) -> None:
        """应接受 dict 格式的样本。"""
        judge_response = json.dumps({"score": 0.5, "reason": "partial"})
        llm = MockLLMGateway(
            responses=[
                LLMResponse(content=judge_response),
                LLMResponse(content=judge_response),
                LLMResponse(content=judge_response),
                LLMResponse(content=judge_response),
            ]
        )
        evaluator = RAGEvaluator(llm_gateway=llm)

        samples = [
            {
                "query": "What is X?",
                "ground_truth_context": "X is a function",
                "ground_truth_answer": "X does something",
            },
        ]

        result = evaluator.evaluate(samples, MockRAGPipeline())
        assert result["sample_count"] == 1
        assert result["faithfulness"] == 0.5

    def test_evaluate_overall_is_weighted_average(self) -> None:
        """综合分数应为加权平均。"""
        judge_response = json.dumps({"score": 1.0, "reason": "perfect"})
        llm = MockLLMGateway(
            responses=[
                LLMResponse(content=judge_response),
                LLMResponse(content=judge_response),
                LLMResponse(content=judge_response),
                LLMResponse(content=judge_response),
            ]
        )
        evaluator = RAGEvaluator(llm_gateway=llm)

        samples = [GoldenSample("q", "ctx", "ans")]
        result = evaluator.evaluate(samples, MockRAGPipeline())

        # All scores = 1.0, so overall = 1.0
        assert result["overall_score"] == pytest.approx(1.0, abs=0.01)


class TestComputeOverall:
    """_compute_overall 方法测试。"""

    def test_all_zero(self) -> None:
        llm = MockLLMGateway()
        evaluator = RAGEvaluator(llm_gateway=llm)
        overall = evaluator._compute_overall(0, 0, 0, 0)
        assert overall == 0.0

    def test_all_one(self) -> None:
        llm = MockLLMGateway()
        evaluator = RAGEvaluator(llm_gateway=llm)
        overall = evaluator._compute_overall(1.0, 1.0, 1.0, 1.0)
        assert overall == pytest.approx(1.0)

    def test_weighted_correctly(self) -> None:
        llm = MockLLMGateway()
        evaluator = RAGEvaluator(llm_gateway=llm)
        overall = evaluator._compute_overall(1.0, 0.0, 0.0, 0.0)
        # Only faithfulness contributes: 0.30
        expected = 1.0 * DIMENSION_WEIGHTS["faithfulness"]
        assert overall == pytest.approx(expected)

    def test_weights_sum_to_one(self) -> None:
        total = sum(DIMENSION_WEIGHTS.values())
        assert pytest.approx(total) == 1.0


class TestLLMAsJudge:
    """LLMAsJudge 辅助类测试。"""

    @pytest.mark.asyncio
    async def test_judge_returns_score_and_reason(self) -> None:
        response = json.dumps({"score": 0.75, "reason": "mostly correct"})
        llm = MockLLMGateway(responses=[LLMResponse(content=response)])
        judge = LLMAsJudge(llm_gateway=llm)

        score, reason = await judge.judge(
            query="What is X?",
            answer="X is something",
            expected="X is a function",
            criterion="faithfulness",
        )
        assert score == 0.75
        assert "mostly correct" in reason

    @pytest.mark.asyncio
    async def test_judge_score_clamped(self) -> None:
        response = json.dumps({"score": 1.5, "reason": "exceeds"})
        llm = MockLLMGateway(responses=[LLMResponse(content=response)])
        judge = LLMAsJudge(llm_gateway=llm)

        score, _ = await judge.judge("q", "a", "e")
        assert score == 1.0

    @pytest.mark.asyncio
    async def test_judge_negative_score_clamped(self) -> None:
        response = json.dumps({"score": -0.5, "reason": "bad"})
        llm = MockLLMGateway(responses=[LLMResponse(content=response)])
        judge = LLMAsJudge(llm_gateway=llm)

        score, _ = await judge.judge("q", "a", "e")
        assert score == 0.0

    @pytest.mark.asyncio
    async def test_judge_invalid_json_returns_zero(self) -> None:
        llm = MockLLMGateway(responses=[LLMResponse(content="not json")])
        judge = LLMAsJudge(llm_gateway=llm)

        score, reason = await judge.judge("q", "a", "e")
        assert score == 0.0
        assert "parse_error" in reason

    @pytest.mark.asyncio
    async def test_judge_json_with_surrounding_text(self) -> None:
        content = (
            "Here is my judgment:\n" + json.dumps({"score": 0.8, "reason": "good"}) + "\nDone."
        )
        llm = MockLLMGateway(responses=[LLMResponse(content=content)])
        judge = LLMAsJudge(llm_gateway=llm)

        score, reason = await judge.judge("q", "a", "e")
        assert score == 0.8

    @pytest.mark.asyncio
    async def test_batch_judge(self) -> None:
        responses = [
            LLMResponse(content=json.dumps({"score": 0.9, "reason": "great"})),
            LLMResponse(content=json.dumps({"score": 0.3, "reason": "poor"})),
        ]
        llm = MockLLMGateway(responses=responses)
        judge = LLMAsJudge(llm_gateway=llm)

        samples = [
            {"query": "q1", "answer": "a1", "expected": "e1"},
            {"query": "q2", "answer": "a2", "expected": "e2"},
        ]
        results = await judge.batch_judge(samples)
        assert len(results) == 2
        assert results[0][0] == 0.9
        assert results[1][0] == 0.3

    def test_judge_prompt_contains_criteria(self) -> None:
        """JUDGE_PROMPT 应包含评分说明。"""
        assert "1.0" in LLMAsJudge.JUDGE_PROMPT
        assert "0.5" in LLMAsJudge.JUDGE_PROMPT
        assert "0.0" in LLMAsJudge.JUDGE_PROMPT
        assert "{query}" in LLMAsJudge.JUDGE_PROMPT
        assert "{answer}" in LLMAsJudge.JUDGE_PROMPT
        assert "{expected}" in LLMAsJudge.JUDGE_PROMPT
