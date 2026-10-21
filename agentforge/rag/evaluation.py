"""评估模块。"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from agentforge.llm.gateway import LLMGateway

logger = logging.getLogger(__name__)

# 尝试导入 ragas，做优雅降级
try:
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False
    ragas_evaluate = None

# 评估维度权重（用于计算综合分）
DIMENSION_WEIGHTS: dict[str, float] = {
    "faithfulness": 0.30,
    "answer_relevancy": 0.30,
    "context_precision": 0.20,
    "context_recall": 0.20,
}


@dataclass
class GoldenSample:
    """基准样本相关组件。

    Attributes:
        query: 查询。
        ground_truth_context: 上下文。
        ground_truth_answer: 回答。
    """

    query: str
    ground_truth_context: str
    ground_truth_answer: str


@dataclass
class EvaluationResult:
    """评估结果相关组件。

    Attributes:
        faithfulness: 字段值。
        answer_relevancy: 回答。
        context_precision: 上下文精确率。
        context_recall: 上下文召回。
        overall_score: 评分。
        sample_count: 样本数量。
        per_sample: 样本。
    """

    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0
    overall_score: float = 0.0
    sample_count: int = 0
    per_sample: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。

        Returns:
            结构化结果字典。
        """
        return {
            "faithfulness": round(self.faithfulness, 4),
            "answer_relevancy": round(self.answer_relevancy, 4),
            "context_precision": round(self.context_precision, 4),
            "context_recall": round(self.context_recall, 4),
            "overall_score": round(self.overall_score, 4),
            "sample_count": self.sample_count,
            "per_sample": self.per_sample,
        }


@runtime_checkable
class RAGPipelineProtocol(Protocol):
    """RAG 管道协议 — 评估器需要调用的 RAG 系统接口。"""

    def retrieve(self, query: str, top_k: int = 5) -> list[str]:
        """检索与查询相关的代码片段。

        Args:
            query: 检索或筛选查询。
            top_k: 返回结果数量上限。

        Returns:
            结果列表。
        """
        ...

    def generate(self, query: str, contexts: list[str]) -> str:
        """基于检索到的上下文生成回答。

        Args:
            query: 检索或筛选查询。
            contexts: 输入参数。

        Returns:
            字符串结果。
        """
        ...


class LLMAsJudge:
    """LLM 裁判 — 用 LLM 做语义断言。

    Attributes:
        CRITERION_DESCRIPTIONS: 描述。
    """

    JUDGE_PROMPT = """You are an expert judge evaluating the quality of AI-generated answers.

## Task
Evaluate whether the generated answer is semantically correct based on the criteria below.

## Query
{query}

## Generated Answer
{answer}

## {criterion_context}

## Expected Answer
{expected}

## Instructions
Respond with ONLY a JSON object:
{{"score": <0.0 to 1.0>, "reason": "<brief explanation>"}}

- 1.0 = The answer fully satisfies the criterion.
- 0.5 = The answer partially satisfies the criterion.
- 0.0 = The answer fails to satisfy the criterion."""

    CRITERION_DESCRIPTIONS: dict[str, str] = {
        "faithfulness": "Reference Context (the answer must be grounded in this context)",
        "answer_relevancy": "Expected Answer Direction (the answer must address this query)",
        "context_precision": "Expected Ground Truth (the retrieved context should contain this)",
        "context_recall": "Ground Truth Context (the retrieved context should cover this)",
    }

    def __init__(self, llm_gateway: LLMGateway) -> None:
        """初始化 LLMAsJudge。

        Args:
            llm_gateway: LLM 网关实例。
        """
        self.llm_gateway = llm_gateway

    async def judge(
        self,
        query: str,
        answer: str,
        expected: str,
        criterion: str = "faithfulness",
    ) -> tuple[float, str]:
        """用 LLM 做语义断言。

        Args:
            query: 检索或筛选查询。
            answer: 回答。
            expected: 输入参数。
            criterion: 输入参数。

        Returns:
            结果元组。
        """
        criterion_context = self.CRITERION_DESCRIPTIONS.get(criterion, "Expected Result")

        prompt = self.JUDGE_PROMPT.format(
            query=query,
            answer=answer,
            criterion_context=criterion_context,
            expected=expected,
        )

        response = await self.llm_gateway.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
        )

        return self._parse_judge_response(response.content)

    def _parse_judge_response(self, output: str) -> tuple[float, str]:
        """解析判定响应。

        Args:
            output: 输出。

        Returns:
            结果元组。
        """
        text = output.strip()

        # 提取 JSON
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return 0.0, "parse_error: no JSON found"

        try:
            data = json.loads(text[start : end + 1])
            score = float(data.get("score", 0.0))
            score = max(0.0, min(1.0, score))
            reason = str(data.get("reason", ""))
            return score, reason
        except (json.JSONDecodeError, ValueError, TypeError):
            return 0.0, "parse_error: invalid JSON"

    async def batch_judge(
        self,
        samples: list[dict[str, str]],
        criterion: str = "faithfulness",
    ) -> list[tuple[float, str]]:
        """批量语义断言。

        Args:
            samples: 样本。
            criterion: 输入参数。

        Returns:
            结果列表。
        """
        results: list[tuple[float, str]] = []
        for sample in samples:
            score, reason = await self.judge(
                query=sample.get("query", ""),
                answer=sample.get("answer", ""),
                expected=sample.get("expected", ""),
                criterion=criterion,
            )
            results.append((score, reason))
        return results


class RAGEvaluator:
    """RAG 检索与生成效果评估器。"""

    def __init__(self, llm_gateway: LLMGateway) -> None:
        """初始化 RAGEvaluator。

        Args:
            llm_gateway: LLM 网关实例。
        """
        self.llm_gateway = llm_gateway
        self._judge = LLMAsJudge(llm_gateway)

    def evaluate(
        self,
        golden_dataset: list[GoldenSample | dict[str, str]],
        rag_pipeline: RAGPipelineProtocol,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """评估输入数据并生成结果。

        Args:
            golden_dataset: 基准数据集。
            rag_pipeline: RAG流水线。
            top_k: 返回结果数量上限。

        Returns:
            结构化结果字典。
        """
        samples = self._normalize_dataset(golden_dataset)

        if not samples:
            logger.warning("Empty golden dataset, returning zero scores")
            return EvaluationResult(sample_count=0).to_dict()

        # 检查 ragas 是否可用
        if not RAGAS_AVAILABLE:
            logger.warning(
                "ragas library not installed. "
                "Install with: pip install ragas. "
                "Falling back to LLM-as-Judge evaluation."
            )
            return self._evaluate_with_llm_judge(samples, rag_pipeline, top_k)

        # 使用 ragas 库评估
        return self._evaluate_with_ragas(samples, rag_pipeline, top_k)

    def _normalize_dataset(
        self,
        golden_dataset: list[GoldenSample | dict[str, str]],
    ) -> list[GoldenSample]:
        """规范化数据集。

        Args:
            golden_dataset: 基准数据集。

        Returns:
            结果列表。
        """
        samples: list[GoldenSample] = []
        for item in golden_dataset:
            if isinstance(item, GoldenSample):
                samples.append(item)
            elif isinstance(item, dict):
                samples.append(
                    GoldenSample(
                        query=item.get("query", ""),
                        ground_truth_context=item.get("ground_truth_context", ""),
                        ground_truth_answer=item.get("ground_truth_answer", ""),
                    )
                )
        return samples

    def _run_rag_for_sample(
        self,
        sample: GoldenSample,
        rag_pipeline: RAGPipelineProtocol,
        top_k: int,
    ) -> tuple[list[str], str]:
        """对单条样本执行 RAG 流程（检索 + 生成）。

        Args:
            sample: 评估样本。
            rag_pipeline: RAG流水线。
            top_k: 返回结果数量上限。

        Returns:
            结果元组。
        """
        retrieved = rag_pipeline.retrieve(sample.query, top_k=top_k)
        answer = rag_pipeline.generate(sample.query, retrieved)
        return retrieved, answer

    def _evaluate_with_ragas(
        self,
        samples: list[GoldenSample],
        rag_pipeline: RAGPipelineProtocol,
        top_k: int,
    ) -> dict[str, Any]:
        """评估使用。

        Args:
            samples: 样本。
            rag_pipeline: RAG流水线。
            top_k: 返回结果数量上限。

        Returns:
            结构化结果字典。
        """
        questions: list[str] = []
        contexts: list[list[str]] = []
        answers: list[str] = []
        ground_truths: list[str] = []
        ground_truth_contexts: list[list[str]] = []

        for sample in samples:
            retrieved, answer = self._run_rag_for_sample(sample, rag_pipeline, top_k)
            questions.append(sample.query)
            contexts.append(retrieved)
            answers.append(answer)
            ground_truths.append(sample.ground_truth_answer)
            ground_truth_contexts.append([sample.ground_truth_context])

        # 构造 ragas 数据集
        try:
            from datasets import Dataset
        except ImportError:
            logger.warning("datasets library not installed, falling back to LLM-as-Judge")
            return self._evaluate_with_llm_judge(samples, rag_pipeline, top_k)

        eval_dataset = Dataset.from_dict(
            {
                "question": questions,
                "contexts": contexts,
                "answer": answers,
                "ground_truth": ground_truths,
                "ground_truth_contexts": ground_truth_contexts,
            }
        )

        # 调用 ragas evaluate
        try:
            result = ragas_evaluate(
                eval_dataset,
                metrics=[
                    faithfulness,
                    answer_relevancy,
                    context_precision,
                    context_recall,
                ],
            )
        except Exception as e:
            logger.error("ragas evaluate failed: %s, falling back to LLM-as-Judge", e)
            return self._evaluate_with_llm_judge(samples, rag_pipeline, top_k)

        # 构造结果
        faithfulness_score = float(result.get("faithfulness", 0.0))
        answer_relevancy_score = float(result.get("answer_relevancy", 0.0))
        context_precision_score = float(result.get("context_precision", 0.0))
        context_recall_score = float(result.get("context_recall", 0.0))

        overall = self._compute_overall(
            faithfulness_score,
            answer_relevancy_score,
            context_precision_score,
            context_recall_score,
        )

        eval_result = EvaluationResult(
            faithfulness=faithfulness_score,
            answer_relevancy=answer_relevancy_score,
            context_precision=context_precision_score,
            context_recall=context_recall_score,
            overall_score=overall,
            sample_count=len(samples),
        )

        logger.info(
            "RAGAS evaluation completed (samples=%d, overall=%.4f)",
            len(samples),
            overall,
        )

        return eval_result.to_dict()

    async def _evaluate_with_llm_judge_async(
        self,
        samples: list[GoldenSample],
        rag_pipeline: RAGPipelineProtocol,
        top_k: int,
    ) -> dict[str, Any]:
        """评估使用LLM判定异步。

        Args:
            samples: 样本。
            rag_pipeline: RAG流水线。
            top_k: 返回结果数量上限。

        Returns:
            结构化结果字典。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        faith_scores: list[float] = []
        relevancy_scores: list[float] = []
        precision_scores: list[float] = []
        recall_scores: list[float] = []
        per_sample: list[dict[str, Any]] = []
        failed = 0

        for sample in samples:
            try:
                retrieved, answer = self._run_rag_for_sample(sample, rag_pipeline, top_k)
                retrieved_text = "\n".join(retrieved)

                f_score, _ = await self._judge.judge(
                    sample.query, answer, retrieved_text, "faithfulness"
                )
                r_score, _ = await self._judge.judge(
                    sample.query,
                    answer,
                    sample.ground_truth_answer,
                    "answer_relevancy",
                )
                cp_score, _ = await self._judge.judge(
                    sample.query,
                    retrieved_text,
                    sample.ground_truth_context,
                    "context_precision",
                )
                cr_score, _ = await self._judge.judge(
                    sample.query,
                    retrieved_text,
                    sample.ground_truth_context,
                    "context_recall",
                )
            except Exception as exc:  # noqa: BLE001 - 记录真实错误，不伪造 0 分
                failed += 1
                logger.error("LLM-as-Judge failed for sample %r: %s", str(sample.query)[:50], exc)
                continue

            faith_scores.append(f_score)
            relevancy_scores.append(r_score)
            precision_scores.append(cp_score)
            recall_scores.append(cr_score)

            per_sample.append(
                {
                    "query": sample.query,
                    "faithfulness": round(f_score, 4),
                    "answer_relevancy": round(r_score, 4),
                    "context_precision": round(cp_score, 4),
                    "context_recall": round(cr_score, 4),
                }
            )

        if not per_sample:
            raise RuntimeError(
                "LLM-as-Judge evaluation produced no scores: all "
                f"{len(samples)} sample(s) failed. No report was generated."
            )

        avg_faith = sum(faith_scores) / len(faith_scores)
        avg_rel = sum(relevancy_scores) / len(relevancy_scores)
        avg_cp = sum(precision_scores) / len(precision_scores)
        avg_cr = sum(recall_scores) / len(recall_scores)

        overall = self._compute_overall(avg_faith, avg_rel, avg_cp, avg_cr)

        result = EvaluationResult(
            faithfulness=avg_faith,
            answer_relevancy=avg_rel,
            context_precision=avg_cp,
            context_recall=avg_cr,
            overall_score=overall,
            sample_count=len(samples),
            per_sample=per_sample,
        )

        logger.info(
            "LLM-as-Judge evaluation completed (samples=%d, failed=%d, overall=%.4f)",
            len(samples),
            failed,
            overall,
        )

        return result.to_dict()

    def _evaluate_with_llm_judge(
        self,
        samples: list[GoldenSample],
        rag_pipeline: RAGPipelineProtocol,
        top_k: int,
    ) -> dict[str, Any]:
        """评估使用LLM判定。

        Args:
            samples: 样本。
            rag_pipeline: RAG流水线。
            top_k: 返回结果数量上限。

        Returns:
            结构化结果字典。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # 没有正在运行的事件循环，安全地创建一次性循环。
            pass
        else:
            raise RuntimeError(
                "RAGEvaluator._evaluate_with_llm_judge must not be called from "
                "inside a running event loop. Use the async variant "
                "_evaluate_with_llm_judge_async instead."
            )

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(
                self._evaluate_with_llm_judge_async(samples, rag_pipeline, top_k)
            )
        finally:
            loop.close()

    def _compute_overall(
        self,
        faithfulness: float,
        answer_relevancy: float,
        context_precision: float,
        context_recall: float,
    ) -> float:
        """计算综合分数（加权平均）。

        Args:
            faithfulness: 输入参数。
            answer_relevancy: 回答。
            context_precision: 上下文精确率。
            context_recall: 上下文召回。

        Returns:
            数值结果。
        """
        return (
            faithfulness * DIMENSION_WEIGHTS["faithfulness"]
            + answer_relevancy * DIMENSION_WEIGHTS["answer_relevancy"]
            + context_precision * DIMENSION_WEIGHTS["context_precision"]
            + context_recall * DIMENSION_WEIGHTS["context_recall"]
        )
