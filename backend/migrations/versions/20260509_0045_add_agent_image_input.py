"""文件功能：为智能体增加模型图片输入能力标记与会话图片附件表。"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260509_0045"
down_revision: str | None = "20260509_0044"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    """检查当前数据库是否存在指定表。"""

    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """检查指定字段是否存在，避免开发库重复迁移失败。"""

    if not _has_table(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    """增加视觉能力配置与图片附件表。"""

    if not _has_column("ai_llm_configs", "supports_image_input"):
        with op.batch_alter_table("ai_llm_configs") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "supports_image_input",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )

    if not _has_table("ai_agent_image_attachments"):
        op.create_table(
            "ai_agent_image_attachments",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("admin_user_id", sa.Integer(), nullable=False),
            sa.Column("workspace_id", sa.Integer(), nullable=False),
            sa.Column("session_id", sa.String(length=128), nullable=False),
            sa.Column("run_id", sa.String(length=128), nullable=True),
            sa.Column("storage_key", sa.Text(), nullable=False),
            sa.Column("original_name", sa.String(length=255), nullable=False),
            sa.Column("content_type", sa.String(length=128), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("promoted_asset_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"]),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.ForeignKeyConstraint(["promoted_asset_id"], ["workspace_assets.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_ai_agent_image_attachments_admin_user_id", "ai_agent_image_attachments", ["admin_user_id"])
        op.create_index("ix_ai_agent_image_attachments_workspace_id", "ai_agent_image_attachments", ["workspace_id"])
        op.create_index("ix_ai_agent_image_attachments_session_id", "ai_agent_image_attachments", ["session_id"])
        op.create_index("ix_ai_agent_image_attachments_run_id", "ai_agent_image_attachments", ["run_id"])
        op.create_index("ix_ai_agent_image_attachments_sha256", "ai_agent_image_attachments", ["sha256"])
        op.create_index("ix_ai_agent_image_attachments_promoted_asset_id", "ai_agent_image_attachments", ["promoted_asset_id"])
        op.create_index("ix_ai_agent_image_attachments_status", "ai_agent_image_attachments", ["status"])


def downgrade() -> None:
    """移除视觉能力配置与图片附件表。"""

    if _has_table("ai_agent_image_attachments"):
        op.drop_index("ix_ai_agent_image_attachments_status", table_name="ai_agent_image_attachments")
        op.drop_index("ix_ai_agent_image_attachments_promoted_asset_id", table_name="ai_agent_image_attachments")
        op.drop_index("ix_ai_agent_image_attachments_sha256", table_name="ai_agent_image_attachments")
        op.drop_index("ix_ai_agent_image_attachments_run_id", table_name="ai_agent_image_attachments")
        op.drop_index("ix_ai_agent_image_attachments_session_id", table_name="ai_agent_image_attachments")
        op.drop_index("ix_ai_agent_image_attachments_workspace_id", table_name="ai_agent_image_attachments")
        op.drop_index("ix_ai_agent_image_attachments_admin_user_id", table_name="ai_agent_image_attachments")
        op.drop_table("ai_agent_image_attachments")

    if _has_column("ai_llm_configs", "supports_image_input"):
        with op.batch_alter_table("ai_llm_configs") as batch_op:
            batch_op.drop_column("supports_image_input")
