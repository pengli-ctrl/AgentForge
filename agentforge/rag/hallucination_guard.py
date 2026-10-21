"""幻觉模块。"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class HallucinationFlag:
    """幻觉标记 — 标记 LLM 输出中疑似幻觉的部分。

    Attributes:
        type: 资源类型。
        detail: 详情。
        item: 条目。
    """

    type: str
    detail: str
    item: str


@dataclass
class VerificationResult:
    """幻觉验证结果。

    Attributes:
        passed: 通过。
        hallucination_count: 幻觉数量。
        flags: 标记。
        cleaned_result: 结果。
    """

    passed: bool
    hallucination_count: int = 0
    flags: list[HallucinationFlag] = field(default_factory=list)
    cleaned_result: dict[str, Any] = field(default_factory=dict)


class HallucinationGuard:
    """幻觉防护层 — 后处理验证 LLM 输出的引用真实性。"""

    def verify_generation(
        self,
        llm_output: str,
        context_chunks: dict[str, str],
    ) -> VerificationResult:
        """验证 LLM 输出中的引用是否真实存在。

        Args:
            llm_output: LLM输出。
            context_chunks: 上下文分片。

        Returns:
            核验结果结果。
        """
        try:
            result = json.loads(llm_output)
        except json.JSONDecodeError:
            return VerificationResult(
                passed=False,
                hallucination_count=1,
                flags=[
                    HallucinationFlag(
                        type="json_parse_error",
                        detail="LLM 输出 JSON 解析失败",
                        item=llm_output[:200],
                    )
                ],
            )

        hallucination_flags: list[HallucinationFlag] = []

        for item in result.get("review_items", []):
            # 检查 1: 引用的 chunk_id 是否真实存在于上下文中
            for chunk_id in item.get("source_chunks", []):
                if chunk_id not in context_chunks:
                    hallucination_flags.append(
                        HallucinationFlag(
                            type="fake_reference",
                            detail=f"引用了不存在的 chunk: {chunk_id}",
                            item=item.get("description", ""),
                        )
                    )

            # 检查 2: evidence 中的代码是否真的出现在引用的 chunk 中
            evidence = item.get("evidence", "")
            referenced_content = " ".join(
                context_chunks.get(cid, "") for cid in item.get("source_chunks", [])
            )
            if evidence and evidence not in referenced_content:
                # 允许一定程度的缩略，但至少要有 50% 的关键词匹配
                evidence_keywords = set(re.findall(r"\w+", evidence))
                context_keywords = set(re.findall(r"\w+", referenced_content))
                overlap = len(evidence_keywords & context_keywords) / max(len(evidence_keywords), 1)
                if overlap < 0.5:
                    hallucination_flags.append(
                        HallucinationFlag(
                            type="fabricated_evidence",
                            detail="引用的代码证据在上下文中不存在",
                            item=item.get("description", ""),
                        )
                    )

            # 检查 3: 是否提到了上下文中不存在的函数名/类名
            mentioned_names = set(re.findall(r"(?:def|class)\s+(\w+)", item.get("description", "")))
            context_names = set(re.findall(r"\w+", referenced_content))
            phantom_names = mentioned_names - context_names
            if phantom_names:
                hallucination_flags.append(
                    HallucinationFlag(
                        type="phantom_reference",
                        detail=f"提到了上下文中不存在的名称: {phantom_names}",
                        item=item.get("description", ""),
                    )
                )

        cleaned_result = self._remove_flagged_items(result, hallucination_flags)

        logger.info(
            "Hallucination verification completed " "(flags=%d, passed=%s)",
            len(hallucination_flags),
            len(hallucination_flags) == 0,
        )

        return VerificationResult(
            passed=len(hallucination_flags) == 0,
            hallucination_count=len(hallucination_flags),
            flags=hallucination_flags,
            cleaned_result=cleaned_result,
        )

    def _remove_flagged_items(
        self,
        result: dict[str, Any],
        flags: list[HallucinationFlag],
    ) -> dict[str, Any]:
        """移除被标记为幻觉的审查意见。

        Args:
            result: 处理结果。
            flags: 标记。

        Returns:
            结构化结果字典。
        """
        flagged_items = {flag.item for flag in flags}
        cleaned = dict(result)

        if "review_items" in cleaned:
            for item in cleaned["review_items"]:
                if item.get("description", "") in flagged_items:
                    item["hallucination_suspected"] = True

        return cleaned
