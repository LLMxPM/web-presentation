"""文件功能：为图片生成任务增加可恢复的外部供应商任务状态。

Revision ID: 20260721_0100
Revises: 20260720_0100
Create Date: 2026-07-21 01:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260721_0100"
down_revision: Union[str, Sequence[str], None] = "20260720_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加外部任务标识、状态、轮询时间和安全供应商元数据。"""

    op.add_column("ai_image_generation_jobs", sa.Column("provider_task_id", sa.String(length=255), nullable=True))
    op.add_column("ai_image_generation_jobs", sa.Column("provider_status", sa.String(length=64), nullable=True))
    op.add_column("ai_image_generation_jobs", sa.Column("provider_request_id", sa.String(length=255), nullable=True))
    op.add_column("ai_image_generation_jobs", sa.Column("provider_state_json", sa.JSON(), nullable=True))
    op.add_column("ai_image_generation_jobs", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ai_image_generation_jobs", sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_ai_image_generation_jobs_provider_task_id", "ai_image_generation_jobs", ["provider_task_id"])
    op.create_index("ix_ai_image_generation_jobs_provider_status", "ai_image_generation_jobs", ["provider_status"])
    op.create_index("ix_ai_image_generation_jobs_next_poll_at", "ai_image_generation_jobs", ["next_poll_at"])


def downgrade() -> None:
    """移除外部供应商任务状态字段。"""

    op.drop_index("ix_ai_image_generation_jobs_next_poll_at", table_name="ai_image_generation_jobs")
    op.drop_index("ix_ai_image_generation_jobs_provider_status", table_name="ai_image_generation_jobs")
    op.drop_index("ix_ai_image_generation_jobs_provider_task_id", table_name="ai_image_generation_jobs")
    op.drop_column("ai_image_generation_jobs", "next_poll_at")
    op.drop_column("ai_image_generation_jobs", "submitted_at")
    op.drop_column("ai_image_generation_jobs", "provider_state_json")
    op.drop_column("ai_image_generation_jobs", "provider_request_id")
    op.drop_column("ai_image_generation_jobs", "provider_status")
    op.drop_column("ai_image_generation_jobs", "provider_task_id")
