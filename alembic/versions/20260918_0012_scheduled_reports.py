"""AgentForge 数据库迁移层：20260918_0012_scheduled_reports。

本模块负责 20260918_0012_scheduled_reports 相关能力，是 数据库迁移层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要函数：upgrade、downgrade。
"""

import sqlalchemy as sa

from alembic import op

revision = "20260918_0012"
down_revision = "20260918_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """执行 upgrade 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
    op.create_table(
        "scheduled_reports",
        sa.Column("report_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("report_type", sa.String(length=16), nullable=False),
        sa.Column("cadence", sa.String(length=16), nullable=False, server_default="daily"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """执行 downgrade 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
    op.drop_table("scheduled_reports")
