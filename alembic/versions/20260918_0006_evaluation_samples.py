"""AgentForge 数据库迁移层：20260918_0006_evaluation_samples。

本模块负责 20260918_0006_evaluation_samples 相关能力，是 数据库迁移层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要函数：upgrade、downgrade。
"""

import sqlalchemy as sa

from alembic import op

revision = "20260918_0006"
down_revision = "20260917_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """执行 upgrade 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
    op.create_table(
        "evaluation_samples",
        sa.Column("sample_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("source_ticket_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("draft_text", sa.Text(), nullable=False),
        sa.Column("final_text", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False, index=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("reviewer_id", sa.String(length=128), nullable=False),
        sa.Column("intent", sa.String(length=128), nullable=True),
        sa.Column("priority", sa.String(length=8), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("provider", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("trace_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """执行 downgrade 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
    op.drop_table("evaluation_samples")
