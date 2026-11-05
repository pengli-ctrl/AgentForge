"""本地 Golden Set 评测工具。"""
from collections.abc import Awaitable, Callable, Mapping, Sequence
async def evaluate_retrieval_cases(cases: Sequence[Mapping], search: Callable[[str], Awaitable[Sequence[str]]]) -> dict[str, float]:
    """计算检索指标。

    Args:
        cases: 评测样本。
        search: 检索函数。

    Returns:
        召回和 MRR。
    """
    if not cases: return {"recall_at_k": 0.0, "mrr": 0.0}
    hits = 0; reciprocal = 0.0
    for case in cases:
        expected = set(case.get("expected_ids", [])); actual = list(await search(str(case.get("query", ""))))
        if expected & set(actual): hits += 1; reciprocal += 1.0 / next(i for i, item in enumerate(actual, 1) if item in expected)
    return {"recall_at_k": hits / len(cases), "mrr": reciprocal / len(cases)}
async def evaluate_answer_cases(cases: Sequence[Mapping], answer: Callable[[str], Awaitable[Mapping]]) -> dict[str, float]:
    """计算回答引用指标。

    Args:
        cases: 评测样本。
        answer: 回答函数。

    Returns:
        引用正确率和拒答率。
    """
    if not cases: return {"citation_accuracy": 0.0, "refusal_rate": 0.0}
    ok = 0; refused = 0
    for case in cases:
        result = await answer(str(case.get("query", ""))); expected = set(case.get("expected_citations", [])); actual = set(result.get("citations", []))
        if expected and expected <= actual: ok += 1
        if not actual and result.get("refused", False): refused += 1
    return {"citation_accuracy": ok / len(cases), "refusal_rate": refused / len(cases)}