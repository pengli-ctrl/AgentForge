"""LLMReranker 单元测试 — LLM 驱动的检索结果重排序。

测试要点：LLM 评分解析、JSON 提取、降级处理、排序逻辑。
"""

from __future__ import annotations

import json

import pytest

from agentforge.llm.gateway import LLMResponse
from agentforge.rag.reranker import RERANK_PROMPT, LLMReranker
from tests.conftest import MockLLMGateway


def _make_chunks(n: int = 5) -> list[dict]:
    """构造测试用 chunk 列表。"""
    return [
        {
            "chunk_id": f"chunk_{i}",
            "content": f"def function_{i}():\n    return {i}",
            "metadata": {"file": f"module_{i}.py", "type": "function", "name": f"function_{i}"},
        }
        for i in range(n)
    ]


class TestRerankerInit:
    """初始化测试。"""

    def test_default_max_chunks(self) -> None:
        """验证 default_max_chunks 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        llm = MockLLMGateway()
        reranker = LLMReranker(llm_gateway=llm)
        assert reranker.max_chunks == 20

    def test_custom_max_chunks(self) -> None:
        """验证 custom_max_chunks 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        llm = MockLLMGateway()
        reranker = LLMReranker(llm_gateway=llm, max_chunks=10)
        assert reranker.max_chunks == 10

    def test_prompt_template_exists(self) -> None:
        """RERANK_PROMPT 模板应包含评分标准。"""
        assert "{query}" in RERANK_PROMPT
        assert "{chunks_text}" in RERANK_PROMPT
        assert "9-10" in RERANK_PROMPT
        assert "7-8" in RERANK_PROMPT
        assert "4-6" in RERANK_PROMPT
        assert "1-3" in RERANK_PROMPT
        assert "0" in RERANK_PROMPT


class TestRerank:
    """rerank 方法测试。"""

    @pytest.mark.asyncio
    async def test_rerank_returns_sorted_results(self) -> None:
        """rerank 应按评分降序返回结果。"""
        scores_json = json.dumps(
            {
                "scores": [
                    {"chunk_id": "chunk_0", "score": 5},
                    {"chunk_id": "chunk_1", "score": 9},
                    {"chunk_id": "chunk_2", "score": 3},
                    {"chunk_id": "chunk_3", "score": 8},
                    {"chunk_id": "chunk_4", "score": 1},
                ]
            }
        )
        llm = MockLLMGateway(responses=[LLMResponse(content=scores_json)])
        reranker = LLMReranker(llm_gateway=llm)

        result = await reranker.rerank(
            query="test query",
            chunks=_make_chunks(5),
            top_k=3,
        )

        assert len(result) == 3
        # 最高分应在第一位
        assert result[0][0] == "chunk_1"
        assert result[0][1] == 9.0
        assert result[1][0] == "chunk_3"
        assert result[1][1] == 8.0
        assert result[2][0] == "chunk_0"
        assert result[2][1] == 5.0

    @pytest.mark.asyncio
    async def test_rerank_empty_chunks(self) -> None:
        """空 chunk 列表应返回空结果。"""
        llm = MockLLMGateway()
        reranker = LLMReranker(llm_gateway=llm)
        result = await reranker.rerank("query", [], top_k=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_rerank_top_k_limits_results(self) -> None:
        """top_k 应限制返回数量。"""
        scores_json = json.dumps(
            {"scores": [{"chunk_id": f"chunk_{i}", "score": 10 - i} for i in range(5)]}
        )
        llm = MockLLMGateway(responses=[LLMResponse(content=scores_json)])
        reranker = LLMReranker(llm_gateway=llm)

        result = await reranker.rerank("query", _make_chunks(5), top_k=2)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_rerank_calls_llm_once(self) -> None:
        """rerank 应只调用 LLM 一次。"""
        scores_json = json.dumps({"scores": [{"chunk_id": "chunk_0", "score": 7}]})
        llm = MockLLMGateway(responses=[LLMResponse(content=scores_json)])
        reranker = LLMReranker(llm_gateway=llm)

        await reranker.rerank("query", _make_chunks(1))
        assert llm.call_count == 1

    @pytest.mark.asyncio
    async def test_rerank_returns_tuples(self) -> None:
        """返回值应为 (chunk_id, score) 元组列表。"""
        scores_json = json.dumps({"scores": [{"chunk_id": "chunk_0", "score": 8}]})
        llm = MockLLMGateway(responses=[LLMResponse(content=scores_json)])
        reranker = LLMReranker(llm_gateway=llm)

        result = await reranker.rerank("query", _make_chunks(1))
        assert len(result) == 1
        assert isinstance(result[0], tuple)
        assert isinstance(result[0][0], str)
        assert isinstance(result[0][1], float)


class TestJSONParsing:
    """JSON 解析测试。"""

    @pytest.mark.asyncio
    async def test_rerank_markdown_wrapped_json(self) -> None:
        """LLM 返回 markdown 包裹的 JSON 时应正确解析。"""
        scores_json = (
            "```json\n"
            + json.dumps(
                {
                    "scores": [
                        {"chunk_id": "chunk_0", "score": 9},
                        {"chunk_id": "chunk_1", "score": 7},
                    ]
                }
            )
            + "\n```"
        )
        llm = MockLLMGateway(responses=[LLMResponse(content=scores_json)])
        reranker = LLMReranker(llm_gateway=llm)

        result = await reranker.rerank("query", _make_chunks(2))
        assert len(result) == 2
        assert result[0][0] == "chunk_0"
        assert result[0][1] == 9.0

    @pytest.mark.asyncio
    async def test_rerank_json_with_extra_text(self) -> None:
        """LLM 返回带额外文本的 JSON 时应正确提取。"""
        content = (
            "Here are the scores:\n"
            + json.dumps({"scores": [{"chunk_id": "chunk_0", "score": 8}]})
            + "\nThat's all."
        )
        llm = MockLLMGateway(responses=[LLMResponse(content=content)])
        reranker = LLMReranker(llm_gateway=llm)

        result = await reranker.rerank("query", _make_chunks(1))
        assert len(result) == 1
        assert result[0][1] == 8.0

    @pytest.mark.asyncio
    async def test_rerank_invalid_json_fallback(self) -> None:
        """LLM 返回无效 JSON 时应降级为原始顺序。"""
        llm = MockLLMGateway(responses=[LLMResponse(content="This is not JSON at all.")])
        reranker = LLMReranker(llm_gateway=llm)

        result = await reranker.rerank("query", _make_chunks(3))
        assert len(result) == 3
        # 降级时所有分数为 0.0
        for chunk_id, score in result:
            assert score == 0.0

    @pytest.mark.asyncio
    async def test_rerank_missing_chunk_id_in_scores(self) -> None:
        """LLM 遗漏某些 chunk 的评分时应给 0 分。"""
        scores_json = json.dumps(
            {
                "scores": [
                    {"chunk_id": "chunk_0", "score": 9},
                    # chunk_1 缺失
                    {"chunk_id": "chunk_2", "score": 5},
                ]
            }
        )
        llm = MockLLMGateway(responses=[LLMResponse(content=scores_json)])
        reranker = LLMReranker(llm_gateway=llm)

        result = await reranker.rerank("query", _make_chunks(3), top_k=3)
        # 说明：该步骤用于实现上述逻辑并保证行为稳定。
        assert result[0][0] == "chunk_0"
        assert result[1][0] == "chunk_2"
        assert result[2][0] == "chunk_1"
        assert result[2][1] == 0.0

    @pytest.mark.asyncio
    async def test_rerank_score_clamped_to_range(self) -> None:
        """评分超出 0-10 范围时应被截断。"""
        scores_json = json.dumps(
            {
                "scores": [
                    {"chunk_id": "chunk_0", "score": 15},
                    {"chunk_id": "chunk_1", "score": -3},
                ]
            }
        )
        llm = MockLLMGateway(responses=[LLMResponse(content=scores_json)])
        reranker = LLMReranker(llm_gateway=llm)

        result = await reranker.rerank("query", _make_chunks(2))
        # 15 被截断为 10.0, -3 被截断为 0.0
        assert result[0][1] == 10.0
        assert result[1][1] == 0.0


class TestFormatChunks:
    """_format_chunks 方法测试。"""

    def test_format_chunks_includes_ids(self) -> None:
        """验证 format_chunks_includes_ids 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        llm = MockLLMGateway()
        reranker = LLMReranker(llm_gateway=llm)
        chunks = _make_chunks(3)
        text = reranker._format_chunks(chunks)
        assert "chunk_0" in text
        assert "chunk_1" in text
        assert "chunk_2" in text

    def test_format_chunks_includes_metadata(self) -> None:
        """验证 format_chunks_includes_metadata 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        llm = MockLLMGateway()
        reranker = LLMReranker(llm_gateway=llm)
        chunks = [
            {
                "chunk_id": "chunk_0",
                "content": "def foo(): pass",
                "metadata": {"file": "test.py", "type": "function", "name": "foo"},
            }
        ]
        text = reranker._format_chunks(chunks)
        assert "file: test.py" in text
        assert "function" in text
        assert "foo" in text

    def test_format_chunks_includes_content(self) -> None:
        """验证 format_chunks_includes_content 对应的业务行为、边界条件和回归场景。

        Returns:
            None，函数执行后的结果。
        """
        llm = MockLLMGateway()
        reranker = LLMReranker(llm_gateway=llm)
        content = "def validate_input(data):\n    return True"
        chunks = [{"chunk_id": "chunk_0", "content": content, "metadata": {}}]
        text = reranker._format_chunks(chunks)
        assert content in text
