"""文件功能：新增普通 Run 进程实例的持久化心跳租约，旧运行态不自动回填。

Revision ID: 20260930_0300
Revises: 20260930_0200
"""

import sqlalchemy as sa
from alembic import op

revision = "20260930_0300"
down_revision = "20260930_0200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """增加独立存活表；历史 owner 未登记，继续按原启动策略/手动取消处理。"""

    op.create_table(
        "ai_agent_process_owners",
        sa.Column("owner_id", sa.String(128), primary_key=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_agent_process_owners_expires_at", "ai_agent_process_owners", ["expires_at"])


def downgrade() -> None:
    """移除心跳表；须先退出依赖该表的新 Backend 实例。"""

    op.drop_index("ix_ai_agent_process_owners_expires_at", table_name="ai_agent_process_owners")
    op.drop_table("ai_agent_process_owners")
