"""
冲突仲裁器 — 防止双 Agent 目标冲突导致的活跃锁（Livelock）。

当两个 Agent 的优化目标不一致且都能修改同一工件时，会产生活跃锁：
两个 Agent 都在忙、都在"正常工作"，但系统在宏观上没有进展。

典型场景：CodeReview 和 TestExecution 形成反馈环
- CodeReview 倾向于重构（改变代码结构）
- TestExecution 倾向于修复测试（要求代码保持特定结构）
- 两个 Agent 像打乒乓球一样来回传递，30 分钟过去任务仍未完成

容错方案：
1. 轮次超限检测 → 升级给 Orchestrator
2. 输出收敛检测 → 两轮输出完全一致，可以结束
3. 输出震荡检测 → 高度相似但有微小差异，冻结一方
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from agentforge.core.event_types import AgentEvent, EventType

logger = logging.getLogger(__name__)


class ConflictArbiter:
    """冲突仲裁器 — 当两个 Agent 的修改产生冲突时，引入仲裁者打破僵局。

    设计原则：
    1. 终止决策权不能共享。两个 Agent 不能同时拥有"修改共享工件"
       和"自行判断是否完成"的权限。
    2. 区分"收敛"和"震荡"。两轮输出完全一致→收敛，可以结束。
       高度相似但有微小差异→震荡，需要冻结一方。
    3. 循环计数只是兜底。真正解决问题的是理解两个 Agent 的修改方向
       是否一致，而不是简单地数循环次数。

    Args:
        max_rounds: 最大允许轮次，超过后升级给 Orchestrator。
    """

    def __init__(self, max_rounds: int = 3) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            max_rounds: int，调用方传入的 max_rounds 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.max_rounds = max_rounds
        self.round_count: dict[str, int] = {}  # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        self.prev_outputs: dict[str, dict[str, Any]] = (
            {}
        )  # 说明：该步骤用于实现上述逻辑并保证行为稳定。

    async def on_agent_complete(
        self,
        event: AgentEvent,
        agent_output: dict[str, Any],
    ) -> AgentEvent:
        """检测 Agent 间的冲突并决定下一步动作。

        三层检测：
        1. 轮次超限 → 升级给 Orchestrator 做决策
        2. 输出收敛 → 两个 Agent 的修改已经趋于稳定，可以结束
        3. 输出震荡 → Agent A 的修改被 Agent B 完全回退

        Args:
            event: Agent 完成事件。
            agent_output: Agent 输出内容。

        Returns:
            处理后的事件（可能是正常流转、升级或冻结）。
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
        """升级到 Orchestrator，带上完整历史，让人工或更高层决策。

        Args:
            event: 原始事件。
            output: Agent 输出。

        Returns:
            冲突升级事件。
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
            event: 原始事件。

        Returns:
            任务完成事件。
        """
        return AgentEvent(
            event_type=EventType.TASK_COMPLETED,
            source_agent="conflict-arbiter",
            correlation_id=event.correlation_id,
            payload={"resolution": "converged"},
        )

    async def _freeze_one_side(self, event: AgentEvent) -> AgentEvent:
        """冻结 TestExecution 的修改权限，只允许 CodeReview 单方面收敛。

        Args:
            event: 原始事件。

        Returns:
            冻结指令事件。
        """
        return AgentEvent(
            event_type=EventType.ROUTE_DECISION,
            source_agent="conflict-arbiter",
            correlation_id=event.correlation_id,
            target_agent="code-review",
            payload={"freeze_tests": True},  # 告诉 CodeReview：不要再改接口
        )

    def _hash_output(self, output: dict[str, Any]) -> str:
        """计算 Agent 输出的哈希值，用于收敛和震荡检测。

        Args:
            output: Agent 输出。

        Returns:
            输出内容的 SHA256 哈希值。
        """
        return hashlib.sha256(
            json.dumps(output, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    def _compute_similarity(self, output1: Any, output2: Any) -> float:
        """计算两个输出的相似度，用于震荡检测。

        使用 token 集合的 Jaccard 相似度：
        1. 将两个输出转为 JSON 字符串
        2. 按空白字符和标点分割为 token 集合
        3. 计算 Jaccard 相似度 = |交集| / |并集|

        Jaccard 相似度简单有效，适合检测"高度相似但有微小差异"的震荡场景。

        Args:
            output1: 第一个输出（当前轮次，dict）。
            output2: 第二个输出（上一轮，dict）。

        Returns:
            相似度（0.0-1.0）。1.0 表示完全相同，0.0 表示完全不同。
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
