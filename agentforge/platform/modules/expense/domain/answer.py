"""回答模块。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExpenseAnswerCitation(BaseModel):
    """报销回答引用相关组件。

    Attributes:
        chunk_id: 分块ID。
        claim_id: 报销单 ID。
        attachment_id: 附件 ID。
        source_uri: 来源URI。
        excerpt: 字段值。
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    claim_id: str
    attachment_id: str | None = None
    source_uri: str
    excerpt: str


class ExpenseRagAnswer(BaseModel):
    """报销RAG回答相关组件。

    Attributes:
        answered: 字段值。
        answer: 回答。
        citations: 引用。
        reason: 变更原因。
        requires_human_review: 要求审核。
    """

    model_config = ConfigDict(extra="forbid")

    answered: bool
    answer: str = ""
    citations: list[ExpenseAnswerCitation] = Field(default_factory=list)
    reason: str = ""
    requires_human_review: bool = True
