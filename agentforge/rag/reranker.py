"""重排器模块。"""

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
    """LLM 驱动的重排序器 — 对检索 Top-K 候选做语义精排。"""

    def __init__(
        self,
        llm_gateway: LLMGateway,
        max_chunks: int = 20,
    ) -> None:
        """初始化 LLMReranker。

        Args:
            llm_gateway: LLM 网关实例。
            max_chunks: 最大分片。
        """
        self.llm_gateway = llm_gateway
        self.max_chunks = max_chunks

    async def rerank(
        self,
        query: str,
        chunks: list[dict[str, Any]],
        top_k: int = 5,
    ) -> list[tuple[str, float]]:
        """对检索结果进行 LLM 精排。

        Args:
            query: 检索或筛选查询。
            chunks: 文本分片列表。
            top_k: 返回结果数量上限。

        Returns:
            结果列表。
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
        """格式化分片。

        Args:
            chunks: 文本分片列表。

        Returns:
            字符串结果。
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
        """解析评分。

        Args:
            llm_output: LLM输出。
            candidates: 输入参数。

        Returns:
            结果列表。
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
        """提取JSON。

        Args:
            text: 待处理文本。

        Returns:
            无结果。
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
