"""任务复杂度估计。

平台只提供协议与规则基线;业务模块可以注入自己的复杂度估计器,
按自身数据分布训练与校准,而不必修改路由核心。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

__all__ = [
    "ComplexityEstimate",
    "ComplexityEstimator",
    "RuleBasedComplexityEstimator",
    "extract_features",
]


_TASK_TYPE_BASE: dict[str, float] = {
    "reasoning": 0.60,
    "code_gen": 0.55,
    "long_context": 0.50,
    "creative": 0.40,
    "classification": 0.15,
    "simple_extraction": 0.10,
}

_COMPLEX_KEYWORDS = (
    "architecture",
    "design",
    "refactor",
    "analyze",
    "prove",
    "multi-step",
    "trade-off",
    "架构",
    "设计",
    "重构",
    "分析",
    "推理",
    "证明",
    "对比",
    "方案",
)

_MULTI_TURN_MARKERS = ("之前", "上次", "继续", "接着", "然后", "刚才", "previous")

_CODE_PATTERN = re.compile(
    r"```|^\s*(def |class |import |from |func |package )|\{.*\}",
    re.MULTILINE,
)


@dataclass(frozen=True)
class ComplexityEstimate:
    """一次复杂度估计的结果。

    Attributes:
        score: 复杂度分数,范围从零到一。
        confidence: 置信度,范围从零到一。
        features: 参与打分的可解释特征。
        reason: 生成该分数的简要依据。
    """

    score: float
    confidence: float
    features: dict[str, float] = field(default_factory=dict)
    reason: str = ""

    def __post_init__(self) -> None:
        """将分数与置信度限制在零到一之间。"""
        object.__setattr__(self, "score", max(0.0, min(1.0, self.score)))
        object.__setattr__(self, "confidence", max(0.0, min(1.0, self.confidence)))


@runtime_checkable
class ComplexityEstimator(Protocol):
    """复杂度估计协议,业务模块可实现并注入。"""

    def estimate(self, text: str, task_type: str) -> ComplexityEstimate:
        """返回复杂度分数与置信度。

        Args:
            text: 待评估的输入文本。
            task_type: 任务类型。

        Returns:
            复杂度估计结果。
        """


def extract_features(text: str, task_type: str) -> dict[str, float]:
    """提取可解释的轻量特征,供规则基线或后续模型使用。

    Args:
        text: 待评估的输入文本。
        task_type: 任务类型。

    Returns:
        特征名到特征值的字典。
    """

    normalized = (text or "").lower()
    char_length = float(len(normalized))
    token_estimate = float(math.ceil(char_length / 4.0))
    code_lines = float(len(_CODE_PATTERN.findall(text or "")))
    keyword_hits = float(sum(1 for kw in _COMPLEX_KEYWORDS if kw in normalized))
    multi_turn = 1.0 if any(marker in normalized for marker in _MULTI_TURN_MARKERS) else 0.0
    return {
        "char_length": char_length,
        "token_estimate": token_estimate,
        "code_lines": code_lines,
        "keyword_hits": keyword_hits,
        "multi_turn": multi_turn,
    }


class RuleBasedComplexityEstimator:
    """确定性规则基线,可解释、无依赖,作为默认与兜底实现。"""

    def __init__(self, max_tokens: int = 2000, max_code_lines: int = 200) -> None:
        """初始化规则基线。

        Args:
            max_tokens: 长度归一化的参考上限。
            max_code_lines: 代码行数归一化的参考上限。
        """
        self._max_tokens = max(1, max_tokens)
        self._max_code_lines = max(1, max_code_lines)

    def estimate(self, text: str, task_type: str) -> ComplexityEstimate:
        """按规则计算复杂度。

        Args:
            text: 待评估的输入文本。
            task_type: 任务类型。

        Returns:
            复杂度估计结果。
        """
        features = extract_features(text, task_type)
        base = _TASK_TYPE_BASE.get(task_type, 0.35)
        length_score = min(1.0, features["token_estimate"] / self._max_tokens)
        code_score = min(1.0, features["code_lines"] / self._max_code_lines)
        keyword_score = min(1.0, features["keyword_hits"] / 5.0)
        multi_turn = features["multi_turn"]

        score = (
            0.35 * base
            + 0.25 * length_score
            + 0.20 * code_score
            + 0.15 * keyword_score
            + 0.05 * multi_turn
        )
        signal_count = sum(
            1.0 for value in (length_score, code_score, keyword_score, multi_turn) if value > 0
        )
        if features["char_length"] < 20:
            confidence = 0.35
        else:
            confidence = min(0.9, 0.5 + 0.1 * signal_count)
        reason = (
            f"task_type={task_type}, tokens={int(features['token_estimate'])}, "
            f"code_lines={int(features['code_lines'])}, "
            f"keyword_hits={int(features['keyword_hits'])}"
        )
        return ComplexityEstimate(
            score=score,
            confidence=confidence,
            features=features,
            reason=reason,
        )
