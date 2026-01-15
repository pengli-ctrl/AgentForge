"""AgentForge 数据库迁移层：20260918_0010_rbac。

本模块负责 20260918_0010_rbac 相关能力，是 数据库迁移层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要函数：upgrade、downgrade。
"""

import sqlalchemy as sa

from alembic import op

revision = "20260918_0010"
down_revision = "20260918_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """执行 upgrade 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
    op.create_table(
        "rbac_roles",
        sa.Column("role_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("built_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "rbac_role_assignments",
        sa.Column("assignment_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("user_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """执行 downgrade 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
    op.drop_table("rbac_role_assignments")
    op.drop_table("rbac_roles")
