"""AgentForge 数据库迁移层：20260918_0011_tenant_quotas。

本模块负责 20260918_0011_tenant_quotas 相关能力，是 数据库迁移层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要函数：upgrade、downgrade。
"""

import sqlalchemy as sa

from alembic import op

revision = "20260918_0011"
down_revision = "20260918_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """执行 upgrade 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
    op.create_table(
        "tenant_quotas",
        sa.Column("tenant_id", sa.String(length=64), primary_key=True),
        sa.Column("monthly_limit", sa.Float(), nullable=False, server_default="0"),
        sa.Column("warning_threshold", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("hard_limit", sa.Float(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """执行 downgrade 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
    op.drop_table("tenant_quotas")
