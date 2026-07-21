"""文件功能：为资源助手成员图片生成任务增加调用关联字段。

Revision ID: 20260723_0100
Revises: 20260721_0100
Create Date: 2026-07-23 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260723_0100"
down_revision: Union[str, Sequence[str], None] = "20260721_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加 deferred 原始调用和可选成员运行关联。"""

    op.add_column("ai_image_generation_jobs", sa.Column("deferred_tool_call_id", sa.String(length=255), nullable=True))
    op.add_column("ai_image_generation_jobs", sa.Column("member_run_id", sa.String(length=128), nullable=True))
    op.execute("UPDATE ai_image_generation_jobs SET deferred_tool_call_id = tool_call_id")
    with op.batch_alter_table("ai_image_generation_jobs") as batch_op:
        batch_op.alter_column("deferred_tool_call_id", nullable=False)
        batch_op.create_foreign_key(
            "fk_ai_image_generation_jobs_member_run_id",
            "ai_agent_member_runs",
            ["member_run_id"],
            ["member_run_id"],
        )
    op.create_index(
        "ix_ai_image_generation_jobs_deferred_tool_call_id",
        "ai_image_generation_jobs",
        ["deferred_tool_call_id"],
    )
    op.create_index("ix_ai_image_generation_jobs_member_run_id", "ai_image_generation_jobs", ["member_run_id"])


def downgrade() -> None:
    """移除成员图片生成调用关联。"""

    op.drop_index("ix_ai_image_generation_jobs_member_run_id", table_name="ai_image_generation_jobs")
    op.drop_index("ix_ai_image_generation_jobs_deferred_tool_call_id", table_name="ai_image_generation_jobs")
    with op.batch_alter_table("ai_image_generation_jobs") as batch_op:
        batch_op.drop_constraint("fk_ai_image_generation_jobs_member_run_id", type_="foreignkey")
        batch_op.drop_column("member_run_id")
        batch_op.drop_column("deferred_tool_call_id")
