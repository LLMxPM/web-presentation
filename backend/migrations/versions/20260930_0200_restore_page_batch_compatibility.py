"""文件功能：前向恢复 N-1 页面 Batch ORM 所需的兼容列，保留回滚窗口。

Revision ID: 20260930_0200
Revises: 20260930_0100

不重写已经应用的删列迁移。当前运行态不使用此列；旧 ORM 完整 SELECT/INSERT
仍需要它，旧实例退出且回滚窗口结束前不得再次删除。恢复值为 0，不能恢复删列前
的历史值；迁移期间应排空旧页面任务，回滚应用时保留当前 schema 并关闭旧迁移器。
"""

from alembic import op
import sqlalchemy as sa

revision = "20260930_0200"
down_revision = "20260930_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """恢复兼容列；服务端默认值允许当前 ORM 继续省略该字段写入。"""

    op.add_column(
        "ai_page_mutation_batches",
        sa.Column("lease_generation", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """回到删列 revision；不用于 N-1 应用回滚，执行前必须退出旧实例。"""

    op.drop_column("ai_page_mutation_batches", "lease_generation")
