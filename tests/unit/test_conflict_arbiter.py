"""ConflictArbiter 单元测试 — 多 Agent 结果冲突检测与仲裁。

测试要点：多Agent结果冲突检测、仲裁策略、优先级排序。
"""

from __future__ import annotations

import pytest

from agentforge.core.event_types import AgentEvent, EventType
from agentforge.safety.conflict_arbiter import ConflictArbiter


def _make_event(
    correlation_id: str = "corr-001",
    source_agent: str = "code-review",
) -> AgentEvent:
    return AgentEvent(
        event_type=EventType.AGENT_COMPLETED,
        source_agent=source_agent,
        correlation_id=correlation_id,
        payload={},
    )


class TestConflictArbiterInit:
    """初始化测试。"""

    def test_default_max_rounds(self) -> None:
        arbiter = ConflictArbiter()
        assert arbiter.max_rounds == 3

    def test_custom_max_rounds(self) -> None:
        arbiter = ConflictArbiter(max_rounds=5)
        assert arbiter.max_rounds == 5

    def test_empty_state_on_init(self) -> None:
        arbiter = ConflictArbiter()
        assert arbiter.round_count == {}
        assert arbiter.prev_outputs == {}


class TestRoundCounting:
    """轮次计数测试。"""

    @pytest.mark.asyncio
    async def test_round_count_increments(self) -> None:
        arbiter = ConflictArbiter(max_rounds=10)
        event = _make_event()
        await arbiter.on_agent_complete(event, {"content": "v1"})
        assert arbiter.round_count["corr-001"] == 1
        await arbiter.on_agent_complete(event, {"content": "v2"})
        assert arbiter.round_count["corr-001"] == 2

    @pytest.mark.asyncio
    async def test_round_count_separate_per_correlation(self) -> None:
        arbiter = ConflictArbiter(max_rounds=10)
        await arbiter.on_agent_complete(_make_event("corr-a"), {"x": 1})
        await arbiter.on_agent_complete(_make_event("corr-b"), {"y": 2})
        assert arbiter.round_count["corr-a"] == 1
        assert arbiter.round_count["corr-b"] == 1


class TestEscalation:
    """轮次超限升级测试。"""

    @pytest.mark.asyncio
    async def test_escalation_after_max_rounds(self) -> None:
        arbiter = ConflictArbiter(max_rounds=2)
        event = _make_event()
        await arbiter.on_agent_complete(event, {"v": 1})
        await arbiter.on_agent_complete(event, {"v": 2})
        # 第三轮应超限
        result = await arbiter.on_agent_complete(event, {"v": 3})
        assert result.event_type == EventType.CONFLICT_ESCALATED
        assert result.source_agent == "conflict-arbiter"
        assert result.target_agent == "orchestrator"
        assert result.payload["resolution"] == "human_review"

    @pytest.mark.asyncio
    async def test_escalation_payload_contains_rounds(self) -> None:
        arbiter = ConflictArbiter(max_rounds=1)
        event = _make_event()
        await arbiter.on_agent_complete(event, {"v": 1})
        result = await arbiter.on_agent_complete(event, {"v": 2})
        assert result.event_type == EventType.CONFLICT_ESCALATED
        assert result.payload["rounds"] == 2


class TestConvergence:
    """输出收敛检测测试。"""

    @pytest.mark.asyncio
    async def test_convergence_detected(self) -> None:
        arbiter = ConflictArbiter(max_rounds=10)
        event = _make_event()
        output = {"review": "looks good", "score": 8}
        first = await arbiter.on_agent_complete(event, output)
        assert first.event_type == EventType.AGENT_COMPLETED  # 正常流转
        second = await arbiter.on_agent_complete(event, output)  # 相同输出
        assert second.event_type == EventType.TASK_COMPLETED
        assert second.payload["resolution"] == "converged"

    @pytest.mark.asyncio
    async def test_no_convergence_with_different_output(self) -> None:
        arbiter = ConflictArbiter(max_rounds=10)
        event = _make_event()
        await arbiter.on_agent_complete(event, {"v": 1})
        second = await arbiter.on_agent_complete(event, {"v": 2})
        assert second.event_type == EventType.AGENT_COMPLETED


class TestOutputHashing:
    """输出哈希测试。"""

    def test_hash_consistent(self) -> None:
        arbiter = ConflictArbiter()
        h1 = arbiter._hash_output({"a": 1, "b": 2})
        h2 = arbiter._hash_output({"b": 2, "a": 1})  # 顺序不同
        assert h1 == h2

    def test_hash_different_for_different_data(self) -> None:
        arbiter = ConflictArbiter()
        h1 = arbiter._hash_output({"a": 1})
        h2 = arbiter._hash_output({"a": 2})
        assert h1 != h2

    def test_hash_returns_hex_string(self) -> None:
        arbiter = ConflictArbiter()
        h = arbiter._hash_output({"x": 1})
        assert isinstance(h, str)
        assert len(h) == 64  # SHA256 hex


class TestSimilarity:
    """相似度计算测试。"""

    def test_similarity_returns_float(self) -> None:
        arbiter = ConflictArbiter()
        sim = arbiter._compute_similarity({"a": 1}, {"a": 1})
        assert isinstance(sim, float)
        assert 0.0 <= sim <= 1.0

    def test_identical_outputs_similarity_one(self) -> None:
        """完全相同的输出，相似度应为 1.0。"""
        arbiter = ConflictArbiter()
        output = {"review": "looks good", "score": 8, "issues": []}
        sim = arbiter._compute_similarity(output, output)
        assert sim == 1.0

    def test_completely_different_outputs_low_similarity(self) -> None:
        """完全不同的输出，相似度应很低。"""
        arbiter = ConflictArbiter()
        sim = arbiter._compute_similarity(
            {"review": "alpha beta gamma"},
            {"status": "delta epsilon zeta"},
        )
        assert sim < 0.3

    def test_partially_similar_outputs(self) -> None:
        """部分相似输出，相似度在 0 和 1 之间。"""
        arbiter = ConflictArbiter()
        sim = arbiter._compute_similarity(
            {"review": "code looks good", "score": 8},
            {"review": "code looks bad", "score": 3},
        )
        assert 0.0 < sim < 1.0

    def test_empty_outputs_similarity_one(self) -> None:
        """两个空字典的相似度为 1.0。"""
        arbiter = ConflictArbiter()
        sim = arbiter._compute_similarity({}, {})
        assert sim == 1.0


class TestOscillationDetection:
    """输出震荡检测测试（使用真实相似度计算）。"""

    @pytest.mark.asyncio
    async def test_oscillation_freezes_one_side(self) -> None:
        """高度相似但非完全一致的输出应触发震荡检测。"""
        arbiter = ConflictArbiter(max_rounds=10)
        event = _make_event()
        # 第一轮输出 — 包含足够多的 token 使得 Jaccard 相似度 > 0.95
        output1 = {
            "review": (
                "code review summary the function is well structured but could "
                "use better error handling and the logic is sound"
            ),
            "score": 7,
            "issues": ["minor style", "missing docstring"],
            "recommendation": "add error handling",
            "details": "the code passes all tests but lacks comprehensive error handling",
        }
        first = await arbiter.on_agent_complete(event, output1)
        assert first.event_type == EventType.AGENT_COMPLETED

        # 第二轮输出 — 只有一个 token 差异（handling -> handlings）
        output2 = dict(output1)
        output2["details"] = "the code passes all tests but lacks comprehensive error handlings"
        second = await arbiter.on_agent_complete(event, output2)
        # 应该检测到震荡
        assert second.event_type == EventType.ROUTE_DECISION
        assert second.payload.get("freeze_tests") is True

    @pytest.mark.asyncio
    async def test_no_oscillation_with_different_output(self) -> None:
        """差异较大的输出不应触发震荡检测。"""
        arbiter = ConflictArbiter(max_rounds=10)
        event = _make_event()
        output1 = {
            "review": "security vulnerability found in authentication module",
            "score": 2,
            "issues": ["sql injection", "xss"],
        }
        first = await arbiter.on_agent_complete(event, output1)
        assert first.event_type == EventType.AGENT_COMPLETED

        output2 = {
            "review": "code style issues, naming conventions not followed",
            "score": 7,
            "issues": ["variable naming"],
        }
        second = await arbiter.on_agent_complete(event, output2)
        # 不应该触发震荡
        assert second.event_type == EventType.AGENT_COMPLETED
