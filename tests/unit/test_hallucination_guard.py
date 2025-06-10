"""HallucinationGuard 单元测试 — 幻觉防护层。

测试要点：引用验证、幻觉检测、置信度评分、防护策略。
"""

from __future__ import annotations

import json

from agentforge.rag.hallucination_guard import (
    HallucinationFlag,
    HallucinationGuard,
    VerificationResult,
)


class TestHallucinationFlag:
    """HallucinationFlag 数据类测试。"""

    def test_flag_fields(self) -> None:
        flag = HallucinationFlag(
            type="fake_reference",
            detail="chunk not found",
            item="review item text",
        )
        assert flag.type == "fake_reference"
        assert flag.detail == "chunk not found"
        assert flag.item == "review item text"


class TestVerificationResult:
    """VerificationResult 数据类测试。"""

    def test_passed_result(self) -> None:
        result = VerificationResult(passed=True)
        assert result.passed is True
        assert result.hallucination_count == 0
        assert result.flags == []

    def test_failed_result(self) -> None:
        result = VerificationResult(
            passed=False,
            hallucination_count=2,
            flags=[
                HallucinationFlag(type="fake_reference", detail="d1", item="i1"),
                HallucinationFlag(type="phantom_reference", detail="d2", item="i2"),
            ],
        )
        assert result.passed is False
        assert result.hallucination_count == 2
        assert len(result.flags) == 2


class TestVerifyGeneration:
    """verify_generation 方法测试。"""

    def test_valid_output_passes(self) -> None:
        guard = HallucinationGuard()
        context_chunks = {"chunk-1": "def add(a, b): return a + b"}
        output = json.dumps(
            {
                "review_items": [
                    {
                        "description": "function add looks good",
                        "source_chunks": ["chunk-1"],
                        "evidence": "def add(a, b): return a + b",
                    }
                ]
            }
        )
        result = guard.verify_generation(output, context_chunks)
        assert result.passed is True
        assert result.hallucination_count == 0

    def test_fake_reference_detected(self) -> None:
        guard = HallucinationGuard()
        context_chunks = {"chunk-1": "def add(a, b): return a + b"}
        output = json.dumps(
            {
                "review_items": [
                    {
                        "description": "review based on chunk",
                        "source_chunks": ["chunk-999"],  # 不存在
                        "evidence": "",
                    }
                ]
            }
        )
        result = guard.verify_generation(output, context_chunks)
        assert result.passed is False
        assert result.hallucination_count >= 1
        assert any(f.type == "fake_reference" for f in result.flags)

    def test_fabricated_evidence_detected(self) -> None:
        guard = HallucinationGuard()
        context_chunks = {"chunk-1": "def add(a, b): return a + b"}
        output = json.dumps(
            {
                "review_items": [
                    {
                        "description": "some review",
                        "source_chunks": ["chunk-1"],
                        "evidence": "completely unrelated code xyz123 unique_string",
                    }
                ]
            }
        )
        result = guard.verify_generation(output, context_chunks)
        assert result.passed is False
        assert any(f.type == "fabricated_evidence" for f in result.flags)

    def test_phantom_reference_detected(self) -> None:
        guard = HallucinationGuard()
        context_chunks = {"chunk-1": "def add(a, b): return a + b"}
        output = json.dumps(
            {
                "review_items": [
                    {
                        "description": "function def non_existent_func is wrong",
                        "source_chunks": ["chunk-1"],
                        "evidence": "",
                    }
                ]
            }
        )
        result = guard.verify_generation(output, context_chunks)
        assert result.passed is False
        assert any(f.type == "phantom_reference" for f in result.flags)

    def test_invalid_json_returns_error(self) -> None:
        guard = HallucinationGuard()
        result = guard.verify_generation("not valid json {{{", {})
        assert result.passed is False
        assert result.hallucination_count == 1
        assert result.flags[0].type == "json_parse_error"

    def test_empty_review_items_passes(self) -> None:
        guard = HallucinationGuard()
        output = json.dumps({"review_items": []})
        result = guard.verify_generation(output, {})
        assert result.passed is True
        assert result.hallucination_count == 0

    def test_multiple_flags_accumulate(self) -> None:
        guard = HallucinationGuard()
        context_chunks = {"chunk-1": "def add(a, b): return a + b"}
        output = json.dumps(
            {
                "review_items": [
                    {
                        "description": "review 1",
                        "source_chunks": ["chunk-1", "chunk-missing"],
                        "evidence": "def add(a, b): return a + b",
                    },
                    {
                        "description": "review 2 with def phantom_func",
                        "source_chunks": ["chunk-1"],
                        "evidence": "",
                    },
                ]
            }
        )
        result = guard.verify_generation(output, context_chunks)
        assert result.hallucination_count >= 2


class TestCleanedResult:
    """清理结果测试。"""

    def test_flagged_items_marked(self) -> None:
        guard = HallucinationGuard()
        context_chunks = {"chunk-1": "content"}
        output = json.dumps(
            {
                "review_items": [
                    {
                        "description": "item with bad ref",
                        "source_chunks": ["chunk-missing"],
                        "evidence": "",
                    }
                ]
            }
        )
        result = guard.verify_generation(output, context_chunks)
        cleaned = result.cleaned_result
        assert "review_items" in cleaned
        assert cleaned["review_items"][0].get("hallucination_suspected") is True

    def test_clean_items_not_marked(self) -> None:
        guard = HallucinationGuard()
        context_chunks = {"chunk-1": "def foo(): pass"}
        output = json.dumps(
            {
                "review_items": [
                    {
                        "description": "foo is good",
                        "source_chunks": ["chunk-1"],
                        "evidence": "def foo(): pass",
                    }
                ]
            }
        )
        result = guard.verify_generation(output, context_chunks)
        cleaned = result.cleaned_result
        item = cleaned["review_items"][0]
        assert item.get("hallucination_suspected") is not True
