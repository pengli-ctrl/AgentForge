"""
LLM Reranker — 用 LLM 对检索结果做精排（第三层防护）。

混合检索（BM25 + FAISS + RRF）返回 Top-20 候选 chunk 后，
用 LLM 对每个 chunk 与 query 的相关性打分（0-10 分），
按评分排序后取 Top-K 交给生成层。

效果对比（50 条 Golden Dataset）：
| 阶段                         | Recall@5 | Recall@10 | 幻觉率 |
|------------------------------|----------|-----------|--------|
| 混合检索后（无 Rerank）       | 0.72     | 0.86      | 26%    |
| + LLM Rerank                  | 0.88     | 0.92      | 18.5%  |

为什么用 LLM 而不是 Cross-Encoder：
1. 代码审查场景中，chunk 的相关性不是简单的词汇匹配
   — query "validate_input 的安全检查逻辑" 需要理解函数语义
2. LLM 能理解代码结构（如"这个 chunk 定义了输入验证，与 query 相关"）
3. Cross-Encoder 需要标注数据训练，50 条 Golden Dataset 不够
4. LLM Rerank 虽然慢（~2s），但只对 Top-20 打分，总成本可控

评分标准：
- 9-10: 直接回答了 query 的核心问题
- 7-8:  与 query 高度相关，提供重要上下文
- 4-6:  部分相关，提供背景信息
- 1-3:  弱相关，几乎不含有用信息
- 0:    完全不相关
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agentforge.llm.gateway import LLMGateway, LLMResponse

logger = logging.getLogger(__name__)

RERANK_PROMPT = """\
You are an expert code reviewer. Your task is to evaluate the relevance of \
code chunks to a given query.

## Query
{query}

## Code Chunks
{chunks_text}

## Scoring Criteria
Score each chunk from 0 to 10 based on how relevant it is to the query:

- **9-10**: The chunk directly answers the core question of the query. \
The code is the primary source of information.
- **7-8**: The chunk is highly relevant and provides important context for \
understanding the query. It contains directly related functions, classes, \
or logic.
- **4-6**: The chunk is partially relevant. It provides background \
information or indirectly related context, but does not directly address \
the query.
- **1-3**: The chunk is weakly related. It contains some overlapping \
keywords or concepts, but almost no useful information for the query.
- **0**: The chunk is completely irrelevant to the query.

## Output Format
Respond with ONLY a JSON object (no markdown, no explanation):

{{"scores": [{{"chunk_id": "chunk_0", "score": 8}}, ...]}}

Ensure every chunk receives a score. Return the JSON directly."""


class LLMReranker:
    """LLM 驱动的重排序器 — 对检索 Top-K 候选做语义精排。

    用 LLM 对每个 chunk 与 query 的相关性评分（0-10），
    按评分降序排序后返回 Top-K。

    设计原则：
    1. 只对 Top-20 候选打分，控制 LLM 调用成本
    2. LLM 返回 JSON 格式评分，用确定性代码解析（不信任 LLM 的排序）
    3. 解析失败时降级为原始顺序（不阻塞流程）

    Args:
        llm_gateway: LLM 网关实例，用于调用 chat 方法。
        max_chunks: 单次重排序的最大 chunk 数量（控制 prompt 长度）。
    """

    def __init__(
        self,
        llm_gateway: LLMGateway,
        max_chunks: int = 20,
    ) -> None:
        self.llm_gateway = llm_gateway
        self.max_chunks = max_chunks

    async def rerank(
        self,
        query: str,
        chunks: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[tuple[str, float]]:
        """对检索结果进行 LLM 精排。

        流程：
        1. 截取前 max_chunks 个候选 chunk
        2. 构造 RERANK_PROMPT，包含 query 和所有 chunk 内容
        3. 调用 LLM 获取评分 JSON
        4. 解析 JSON，按评分降序排序
        5. 返回 Top-K 的 (chunk_id, score) 元组列表

        Args:
            query: 用户查询字符串。
            chunks: 候选 chunk 列表，每个 chunk 是一个 dict，
                   至少包含 ``chunk_id`` 和 ``content`` 两个键。
            top_k: 返回的 Top-K 数量。

        Returns:
            按评分降序排列的 ``(chunk_id, score)`` 元组列表，长度 <= top_k。
        """
        if not chunks:
            return []

        # 截取前 max_chunks 个候选
        candidates = chunks[: self.max_chunks]

        # 构造 chunk 文本
        chunks_text = self._format_chunks(candidates)

        # 构造 prompt
        prompt = RERANK_PROMPT.format(
            query=query,
            chunks_text=chunks_text,
        )

        # 调用 LLM
        messages = [
            {"role": "system", "content": "You are a code relevance scoring assistant."},
            {"role": "user", "content": prompt},
        ]

        logger.info(
            "LLM rerank started (query='%s', num_chunks=%d, top_k=%d)",
            query[:80],
            len(candidates),
            top_k,
        )

        response: LLMResponse = await self.llm_gateway.chat(
            messages,
            temperature=0.0,
        )

        # 解析 LLM 返回的 JSON 评分
        scores = self._parse_scores(response.content, candidates)

        # 按评分降序排序
        sorted_scores = sorted(scores, key=lambda x: x[1], reverse=True)

        # 返回 Top-K
        result = sorted_scores[:top_k]

        logger.info(
            "LLM rerank completed (query='%s', returned=%d, top_score=%.1f)",
            query[:80],
            len(result),
            result[0][1] if result else 0.0,
        )

        return result

    def _format_chunks(self, chunks: list[dict[str, Any]]) -> str:
        """将 chunk 列表格式化为 prompt 文本。

        每个 chunk 格式为：
            [chunk_0] (file: xxx.py, type: function, name: validate_input)
            <content>

        Args:
            chunks: chunk 字典列表。

        Returns:
            格式化后的文本。
        """
        lines: list[str] = []
        for i, chunk in enumerate(chunks):
            chunk_id = chunk.get("chunk_id", f"chunk_{i}")
            content = chunk.get("content", "")
            metadata = chunk.get("metadata", {})

            # 附加元信息帮助 LLM 理解上下文
            meta_parts: list[str] = []
            if metadata:
                for key in ("file", "type", "name"):
                    val = metadata.get(key, metadata.get(key))
                    if val:
                        meta_parts.append(f"{key}: {val}")

            header = f"[{chunk_id}]"
            if meta_parts:
                header += f" ({', '.join(meta_parts)})"

            lines.append(f"{header}\n{content}")
            lines.append("")  # 空行分隔

        return "\n".join(lines)

    def _parse_scores(
        self,
        llm_output: str,
        candidates: list[dict[str, Any]],
    ) -> list[tuple[str, float]]:
        """解析 LLM 返回的评分 JSON。

        期望格式：
            {"scores": [{"chunk_id": "chunk_0", "score": 8}, ...]}

        解析失败时降级为：所有 chunk 获得相同分数（保持原始顺序）。

        Args:
            llm_output: LLM 返回的文本。
            candidates: 候选 chunk 列表（用于降级时保持顺序）。

        Returns:
            ``(chunk_id, score)`` 元组列表。
        """
        # 尝试提取 JSON（LLM 可能在 JSON 前后加了 markdown 标记）
        json_str = self._extract_json(llm_output)

        if json_str is None:
            logger.warning("Failed to parse LLM rerank scores, falling back to original order")
            return [(c.get("chunk_id", f"chunk_{i}"), 0.0) for i, c in enumerate(candidates)]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning("LLM rerank JSON decode failed, falling back to original order")
            return [(c.get("chunk_id", f"chunk_{i}"), 0.0) for i, c in enumerate(candidates)]

        scores_list = data.get("scores", [])
        if not isinstance(scores_list, list):
            scores_list = []

        # 构建 chunk_id -> score 映射
        score_map: dict[str, float] = {}
        for item in scores_list:
            if not isinstance(item, dict):
                continue
            chunk_id = item.get("chunk_id", "")
            score = item.get("score", 0)
            # 确保分数在 0-10 范围内
            try:
                score = float(score)
                score = max(0.0, min(10.0, score))
            except (TypeError, ValueError):
                score = 0.0
            if chunk_id:
                score_map[chunk_id] = score

        # 按候选顺序构建结果（缺失的 chunk 给 0 分）
        results: list[tuple[str, float]] = []
        for i, chunk in enumerate(candidates):
            chunk_id = chunk.get("chunk_id", f"chunk_{i}")
            score = score_map.get(chunk_id, 0.0)
            results.append((chunk_id, score))

        return results

    def _extract_json(self, text: str) -> str | None:
        """从 LLM 输出中提取 JSON 字符串。

        处理 LLM 可能在 JSON 前后添加的 markdown 标记（```json ... ```）。

        Args:
            text: LLM 输出文本。

        Returns:
            提取的 JSON 字符串，提取失败返回 None。
        """
        text = text.strip()

        # 尝试直接解析
        if text.startswith("{"):
            return text

        # 尝试从 markdown 代码块中提取
        if "```" in text:
            # 找第一个 ``` 后的内容
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                # 去掉可能的语言标记（json、JSON 等）
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{") and part.rstrip().endswith("}"):
                    return part.rstrip()

        # 尝试找到第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]

        return None
