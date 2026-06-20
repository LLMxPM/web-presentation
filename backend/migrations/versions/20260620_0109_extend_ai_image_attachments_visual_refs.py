"""扩展智能体图片附件，支持工具图片与模型 URL 短时复用。

Revision ID: 20260620_0109
Revises: 20260620_0108
Create Date: 2026-06-20 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260620_0109"
down_revision: Union[str, Sequence[str], None] = "20260620_0108"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为 Agent 图片附件补充来源、工具上下文和短时复用模型 URL 字段。"""

    op.add_column("ai_agent_image_attachments", sa.Column("source_kind", sa.String(length=32), nullable=True))
    op.add_column("ai_agent_image_attachments", sa.Column("tool_name", sa.String(length=128), nullable=True))
    op.add_column("ai_agent_image_attachments", sa.Column("tool_call_id", sa.String(length=255), nullable=True))
    op.add_column("ai_agent_image_attachments", sa.Column("source_payload_json", sa.JSON(), nullable=True))
    op.add_column("ai_agent_image_attachments", sa.Column("model_url", sa.Text(), nullable=True))
    op.add_column("ai_agent_image_attachments", sa.Column("model_url_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_agent_image_attachments", sa.Column("model_url_last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_agent_image_attachments", sa.Column("owned_object", sa.Boolean(), nullable=True))
    op.execute("UPDATE ai_agent_image_attachments SET source_kind = 'user_upload' WHERE source_kind IS NULL")
    op.execute("UPDATE ai_agent_image_attachments SET owned_object = TRUE WHERE owned_object IS NULL")
    with op.batch_alter_table("ai_agent_image_attachments") as batch_op:
        batch_op.alter_column("source_kind", existing_type=sa.String(length=32), nullable=False)
        batch_op.alter_column("owned_object", existing_type=sa.Boolean(), nullable=False)
        batch_op.create_index("ix_ai_agent_image_attachments_source_kind", ["source_kind"])
        batch_op.create_index("ix_ai_agent_image_attachments_tool_name", ["tool_name"])
        batch_op.create_index("ix_ai_agent_image_attachments_tool_call_id", ["tool_call_id"])


def downgrade() -> None:
    """回滚 Agent 图片附件扩展字段。"""

    with op.batch_alter_table("ai_agent_image_attachments") as batch_op:
        batch_op.drop_index("ix_ai_agent_image_attachments_tool_call_id")
        batch_op.drop_index("ix_ai_agent_image_attachments_tool_name")
        batch_op.drop_index("ix_ai_agent_image_attachments_source_kind")
    op.drop_column("ai_agent_image_attachments", "owned_object")
    op.drop_column("ai_agent_image_attachments", "model_url_last_used_at")
    op.drop_column("ai_agent_image_attachments", "model_url_expires_at")
    op.drop_column("ai_agent_image_attachments", "model_url")
    op.drop_column("ai_agent_image_attachments", "source_payload_json")
    op.drop_column("ai_agent_image_attachments", "tool_call_id")
    op.drop_column("ai_agent_image_attachments", "tool_name")
    op.drop_column("ai_agent_image_attachments", "source_kind")
