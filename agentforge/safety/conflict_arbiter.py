"""冲突模块。"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from agentforge.core.event_types import AgentEvent, EventType

logger = logging.getLogger(__name__)


class ConflictArbiter:
    """冲突相关组件。"""

    def __init__(self, max_rounds: int = 3) -> None:
        """初始化 ConflictArbiter。

        Args:
            max_rounds: 最大轮次。
        """
        self.max_rounds = max_rounds
        self.round_count: dict[str, int] = {}
        self.prev_outputs: dict[str, dict[str, Any]] = {}

    async def on_agent_complete(
        self,
        event: AgentEvent,
        agent_output: dict[str, Any],
    ) -> AgentEvent:
        """处理时智能体完成。

        Args:
            event: 待处理事件。
            agent_output: 智能体输出。

        Returns:
            智能体事件结果。
        """
        key = event.correlation_id
        self.round_count[key] = self.round_count.get(key, 0) + 1

        # 检测 1: 轮次超限 → 升级给 Orchestrator 做决策
        if self.round_count[key] > self.max_rounds:
            logger.warning(
                "Conflict escalated (correlation_id=%s, rounds=%d)",
                key,
                self.round_count[key],
            )
            return await self._escalate(event, agent_output)

        # 计算当前输出的哈希
        output_hash = self._hash_output(agent_output)

        # 检测 2: 输出收敛 → 两个 Agent 的修改已经趋于稳定
        if key in self.prev_outputs:
            prev_hash = self._hash_output(self.prev_outputs[key])
            if prev_hash == output_hash:
                logger.info(
                    "Output converged (correlation_id=%s), marking complete",
                    key,
                )
                return await self._mark_complete(event)

        # 检测 3: 输出震荡 → Agent A 的修改被 Agent B 完全回退
        if key in self.prev_outputs:
            similarity = self._compute_similarity(
                agent_output,
                self.prev_outputs[key],
            )
            if similarity > 0.95:
                logger.warning(
                    "Output oscillation detected (correlation_id=%s, "
                    "similarity=%.3f), freezing one side",
                    key,
                    similarity,
                )
                return await self._freeze_one_side(event)

        self.prev_outputs[key] = agent_output
        return event  # 正常流转

    async def _escalate(
        self,
        event: AgentEvent,
        output: dict[str, Any],
    ) -> AgentEvent:
        """升级冲突。

        Args:
            event: 待处理事件。
            output: 输出。

        Returns:
            智能体事件结果。
        """
        return AgentEvent(
            event_type=EventType.CONFLICT_ESCALATED,
            source_agent="conflict-arbiter",
            correlation_id=event.correlation_id,
            target_agent="orchestrator",
            payload={
                "conflict_agents": ["code-review", "test-execution"],
                "rounds": self.round_count.get(event.correlation_id, 0),
                "resolution": "human_review",  # 强制人工介入
            },
        )

    async def _mark_complete(self, event: AgentEvent) -> AgentEvent:
        """标记任务完成。

        Args:
            event: 待处理事件。

        Returns:
            智能体事件结果。
        """
        return AgentEvent(
            event_type=EventType.TASK_COMPLETED,
            source_agent="conflict-arbiter",
            correlation_id=event.correlation_id,
            payload={"resolution": "converged"},
        )

    async def _freeze_one_side(self, event: AgentEvent) -> AgentEvent:
        """冻结单个侧。

        Args:
            event: 待处理事件。

        Returns:
            智能体事件结果。
        """
        return AgentEvent(
            event_type=EventType.ROUTE_DECISION,
            source_agent="conflict-arbiter",
            correlation_id=event.correlation_id,
            target_agent="code-review",
            payload={"freeze_tests": True},  # 告诉 CodeReview：不要再改接口
        )

    def _hash_output(self, output: dict[str, Any]) -> str:
        """处理哈希输出。

        Args:
            output: 输出。

        Returns:
            字符串结果。
        """
        return hashlib.sha256(
            json.dumps(output, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    def _compute_similarity(self, output1: Any, output2: Any) -> float:
        """计算两个输出的相似度，用于震荡检测。

        Args:
            output1: 输入参数。
            output2: 输入参数。

        Returns:
            数值结果。
        """
        # 将输出转为规范化 JSON 字符串
        try:
            str1 = json.dumps(output1, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            str1 = str(output1)

        try:
            str2 = json.dumps(output2, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            str2 = str(output2)

        # 分割为 token 集合（按标点和空白分割）
        import re

        tokens1 = set(re.findall(r"\w+", str1.lower()))
        tokens2 = set(re.findall(r"\w+", str2.lower()))

        # Jaccard 相似度 = |交集| / |并集|
        if not tokens1 and not tokens2:
            return 1.0  # 两个空集视为完全相同

        union = tokens1 | tokens2
        if not union:
            return 0.0

        intersection = tokens1 & tokens2
        return len(intersection) / len(union)
