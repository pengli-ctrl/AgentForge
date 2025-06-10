"""
RAGAS 评估框架 — RAG 系统的质量评估（第五层防护）。

评估不需要实时运行，而是在迭代后离线评估。
Golden Dataset 是人工标注的标准答案集（约 50 条），
用于衡量 RAG 系统在四个维度上的表现。

四个评估维度：
1. **Faithfulness（忠实度）**：生成内容是否忠于检索到的上下文，
   不编造信息。低忠实度意味着 LLM 在"幻觉"。
2. **Answer Relevancy（回答相关性）**：生成的回答与用户查询的相关程度。
   低相关性意味着回答偏离了用户意图。
3. **Context Precision（上下文精确度）**：检索到的上下文中有多少
   是真正有用的。低精确度意味着检索系统塞入了大量无关信息。
4. **Context Recall（上下文召回率）**：标准答案所需的信息有多少
   被检索到了。低召回率意味着检索系统遗漏了关键信息。

这四个维度覆盖了 RAG 系统的两个核心环节：
- 检索质量（Context Precision + Context Recall）
- 生成质量（Faithfulness + Answer Relevancy）

整体分数 = 四个维度的加权平均。
"""

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
    from ragas import evaluate as ragas_evaluate  # type: ignore[import-untyped]
    from ragas.metrics import (  # type: ignore[import-untyped]
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False
    ragas_evaluate = None  # type: ignore[assignment]

# 评估维度权重（用于计算综合分）
DIMENSION_WEIGHTS: dict[str, float] = {
    "faithfulness": 0.30,
    "answer_relevancy": 0.30,
    "context_precision": 0.20,
    "context_recall": 0.20,
}


@dataclass
class GoldenSample:
    """Golden Dataset 中的一条标准样本。

    人工标注的"标准答案"，用于评估 RAG 系统输出质量。

    Attributes:
        query: 用户查询。
        ground_truth_context: 标准答案所需的上下文内容。
        ground_truth_answer: 标准答案。
    """

    query: str
    ground_truth_context: str
    ground_truth_answer: str


@dataclass
class EvaluationResult:
    """RAGAS 评估结果。

    Attributes:
        faithfulness: 忠实度分数（0-1）。
        answer_relevancy: 回答相关性分数（0-1）。
        context_precision: 上下文精确度分数（0-1）。
        context_recall: 上下文召回率分数（0-1）。
        overall_score: 综合分数（0-1），加权平均。
        sample_count: 评估样本数。
        per_sample: 每条样本的详细分数。
    """

    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0
    overall_score: float = 0.0
    sample_count: int = 0
    per_sample: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式。"""
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
        """检索与查询相关的代码片段。"""
        ...

    def generate(self, query: str, contexts: list[str]) -> str:
        """基于检索到的上下文生成回答。"""
        ...


class LLMAsJudge:
    """LLM 裁判 — 用 LLM 做语义断言。

    不检查精确文本匹配，而是检查语义是否符合预期。
    用于评估 LLM 生成的回答在语义层面是否正确，
    即使措辞不同但语义一致也算通过。

    核心场景：
    - 检查 LLM 回答是否包含 ground truth 的关键信息点
    - 检查 LLM 回答是否与上下文一致（不编造）
    - 检查回答是否偏离了查询意图

    Args:
        llm_gateway: LLM 网关实例。
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
            query: 用户查询。
            answer: 被评估的回答。
            expected: 标准答案或预期上下文。
            criterion: 评估维度（faithfulness / answer_relevancy 等）。

        Returns:
            ``(score, reason)`` 元组，score 在 0.0-1.0 之间。
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
        """解析 LLM 裁判的 JSON 响应。

        Args:
            output: LLM 返回的文本。

        Returns:
            ``(score, reason)`` 元组。解析失败返回 ``(0.0, "parse_error")``。
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
            samples: 每条包含 query, answer, expected 三个键。
            criterion: 评估维度。

        Returns:
            ``(score, reason)`` 元组列表。
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
    """RAGAS 评估器 — 对 RAG 系统进行全面质量评估。

    评估流程：
    1. 遍历 Golden Dataset 中的每条样本
    2. 用 RAG 管道生成回答（检索 + 生成）
    3. 用 RAGAS 库的四个维度指标评估
    4. 返回结构化评估结果

    如果 ragas 库未安装，降级为 LLM-as-Judge 模式：
    用 LLM 做语义断言代替 RAGAS 的量化指标。

    Args:
        llm_gateway: LLM 网关实例（RAGAS 和 LLM-as-Judge 都需要）。
    """

    def __init__(self, llm_gateway: LLMGateway) -> None:
        self.llm_gateway = llm_gateway
        self._judge = LLMAsJudge(llm_gateway)

    def evaluate(
        self,
        golden_dataset: list[GoldenSample | dict[str, str]],
        rag_pipeline: RAGPipelineProtocol,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """评估 RAG 系统在 Golden Dataset 上的表现。

        Args:
            golden_dataset: Golden Dataset 样本列表。
            rag_pipeline: RAG 管道实例，需实现 retrieve 和 generate 方法。
            top_k: 检索时返回的 Top-K 数量。

        Returns:
            评估结果字典，包含四个维度分数 + 综合分 + 每条样本详情。
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
        """将数据集统一转为 GoldenSample 列表。

        Args:
            golden_dataset: 原始数据集，元素可以是 GoldenSample 或 dict。

        Returns:
            GoldenSample 列表。
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
            sample: Golden 样本。
            rag_pipeline: RAG 管道实例。
            top_k: 检索 Top-K。

        Returns:
            ``(retrieved_contexts, generated_answer)`` 元组。
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
        """使用 ragas 库进行正式评估。

        构造 ragas 评估数据集，调用 ragas.evaluate 函数。

        Args:
            samples: GoldenSample 列表。
            rag_pipeline: RAG 管道实例。
            top_k: 检索 Top-K。

        Returns:
            评估结果字典。
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
            from datasets import Dataset  # type: ignore[import-untyped]
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

    def _evaluate_with_llm_judge(
        self,
        samples: list[GoldenSample],
        rag_pipeline: RAGPipelineProtocol,
        top_k: int,
    ) -> dict[str, Any]:
        """使用 LLM-as-Judge 降级评估（ragas 未安装时）。

        用 LLM 对每条样本做语义断言，近似四个维度。
        通过 asyncio.run 在同步方法中调用异步 LLM。

        Args:
            samples: GoldenSample 列表。
            rag_pipeline: RAG 管道实例。
            top_k: 检索 Top-K。

        Returns:
            评估结果字典。
        """
        faith_scores: list[float] = []
        relevancy_scores: list[float] = []
        precision_scores: list[float] = []
        recall_scores: list[float] = []
        per_sample: list[dict[str, Any]] = []

        for sample in samples:
            retrieved, answer = self._run_rag_for_sample(sample, rag_pipeline, top_k)
            retrieved_text = "\n".join(retrieved)

            # 在同步上下文中运行异步 LLM 调用
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                f_score, _ = loop.run_until_complete(
                    self._judge.judge(sample.query, answer, retrieved_text, "faithfulness")
                )
                r_score, _ = loop.run_until_complete(
                    self._judge.judge(
                        sample.query,
                        answer,
                        sample.ground_truth_answer,
                        "answer_relevancy",
                    )
                )
                cp_score, _ = loop.run_until_complete(
                    self._judge.judge(
                        sample.query,
                        retrieved_text,
                        sample.ground_truth_context,
                        "context_precision",
                    )
                )
                cr_score, _ = loop.run_until_complete(
                    self._judge.judge(
                        sample.query,
                        retrieved_text,
                        sample.ground_truth_context,
                        "context_recall",
                    )
                )
                loop.close()
            except RuntimeError:
                # 已有事件循环运行中，创建 task 方式不适用于同步上下文
                f_score = 0.0
                r_score = 0.0
                cp_score = 0.0
                cr_score = 0.0

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

        avg_faith = sum(faith_scores) / len(faith_scores) if faith_scores else 0.0
        avg_rel = sum(relevancy_scores) / len(relevancy_scores) if relevancy_scores else 0.0
        avg_cp = sum(precision_scores) / len(precision_scores) if precision_scores else 0.0
        avg_cr = sum(recall_scores) / len(recall_scores) if recall_scores else 0.0

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
            "LLM-as-Judge evaluation completed (samples=%d, overall=%.4f)",
            len(samples),
            overall,
        )

        return result.to_dict()

    def _compute_overall(
        self,
        faithfulness: float,
        answer_relevancy: float,
        context_precision: float,
        context_recall: float,
    ) -> float:
        """计算综合分数（加权平均）。

        权重：
        - Faithfulness: 30%（忠实度最重要，防幻觉）
        - Answer Relevancy: 30%（回答必须切题）
        - Context Precision: 20%（检索质量）
        - Context Recall: 20%（检索覆盖）

        Args:
            faithfulness: 忠实度分数。
            answer_relevancy: 回答相关性分数。
            context_precision: 上下文精确度分数。
            context_recall: 上下文召回率分数。

        Returns:
            综合分数（0-1）。
        """
        return (
            faithfulness * DIMENSION_WEIGHTS["faithfulness"]
            + answer_relevancy * DIMENSION_WEIGHTS["answer_relevancy"]
            + context_precision * DIMENSION_WEIGHTS["context_precision"]
            + context_recall * DIMENSION_WEIGHTS["context_recall"]
        )
