"""文件功能：持久化创建候选编码与截图待发布对象，支持 SQLite/PG 升降级。

Revision ID: 20261019_0100
Revises: 20261018_0100
"""

import sqlalchemy as sa
from alembic import op

revision = "20261019_0100"
down_revision = "20261018_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增可空候选编码，历史任务保持原行为；待发布图片不提前创建业务页面。"""
    for table in ("ai_page_mutation_jobs", "api_mutation_jobs"):
        op.add_column(table, sa.Column("candidate_code", sa.String(64), nullable=True))
    op.create_table("page_screenshot_artifacts",
                    sa.Column("artifact_id", sa.String(64), primary_key=True),
                    sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=False),
                    sa.Column("page_id", sa.Integer(), sa.ForeignKey("pages.id"), nullable=True),
                    sa.Column("version_no", sa.Integer(), nullable=True),
                    sa.Column("sha256", sa.String(64), nullable=False),
                    sa.Column("storage_key", sa.String(512), nullable=False),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    for column in ("workspace_id", "page_id", "expires_at"):
        op.create_index(f"ix_page_screenshot_artifacts_{column}", "page_screenshot_artifacts", [column])
    op.create_index("ix_screenshot_artifacts_page_hash", "page_screenshot_artifacts", ["page_id", "sha256"])


def downgrade() -> None:
    """移除新持久字段；已存 PNG 由存储运维保留，降级不删除业务文件。"""
    op.drop_table("page_screenshot_artifacts")
    for table in ("ai_page_mutation_jobs", "api_mutation_jobs"):
        op.drop_column(table, "candidate_code")
