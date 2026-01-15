"""AgentForge 数据库迁移层：20260917_0005_audit_actor。

本模块负责 20260917_0005_audit_actor 相关能力，是 数据库迁移层 的组成部分。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 涉及租户、任务、审计或成本的数据必须保持隔离和可追踪。
- 关键路径应保留日志、指标或链路追踪信息。
- 主要函数：upgrade、downgrade。
"""

import sqlalchemy as sa

from alembic import op

revision = "20260917_0005"
down_revision = "20260917_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """执行 upgrade 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
    op.add_column(
        "audit_events",
        sa.Column("actor_type", sa.String(length=32), nullable=False, server_default="system"),
    )
    op.add_column(
        "audit_events",
        sa.Column("actor_id", sa.String(length=128), nullable=False, server_default="agentforge"),
    )
    op.add_column("audit_events", sa.Column("trace_id", sa.String(length=64), nullable=True))
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_resource_type", "audit_events", ["resource_type"])
    op.create_index("ix_audit_events_resource_id", "audit_events", ["resource_id"])
    op.create_index("ix_audit_events_trace_id", "audit_events", ["trace_id"])


def downgrade() -> None:
    """执行 downgrade 对应的逻辑，并返回处理结果。

    Returns:
        None，函数执行后的结果。
    """
    op.drop_index("ix_audit_events_trace_id", table_name="audit_events")
    op.drop_index("ix_audit_events_resource_id", table_name="audit_events")
    op.drop_index("ix_audit_events_resource_type", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_column("audit_events", "trace_id")
    op.drop_column("audit_events", "actor_id")
    op.drop_column("audit_events", "actor_type")
