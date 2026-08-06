"""文件功能：把内容助手会话迁移为工作空间级偏好，并归档不兼容的旧会话。

Revision ID: 20260806_0100
Revises: 20260805_0200
Create Date: 2026-08-06 01:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_0100"
down_revision: Union[str, Sequence[str], None] = "20260805_0200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """取消旧运行、归档旧会话，再替换会话 scope 字段。"""

    op.execute(
        """
        UPDATE ai_agent_requirements
        SET status = 'cancelled', resolved_at = CURRENT_TIMESTAMP
        WHERE status = 'pending'
          AND run_id IN (
              SELECT run_id FROM ai_agent_runs
              WHERE agent_id = 'agent-coordinator'
                AND status IN ('pending', 'running', 'paused', 'waiting_external', 'cancelling')
          )
        """
    )
    op.execute(
        """
        UPDATE ai_page_mutation_jobs
        SET status = 'cancelled', cancel_requested_at = CURRENT_TIMESTAMP,
            finished_at = CURRENT_TIMESTAMP, error_code = 'AI_SESSION_SCOPE_MIGRATED',
            error_message = '内容助手会话范围升级，旧任务已取消。'
        WHERE status IN ('pending', 'running')
          AND run_id IN (
              SELECT run_id FROM ai_agent_runs
              WHERE agent_id = 'agent-coordinator'
                AND status IN ('pending', 'running', 'paused', 'waiting_external', 'cancelling')
          )
        """
    )
    op.execute(
        """
        UPDATE ai_image_generation_jobs
        SET status = 'cancelled', cancel_requested_at = CURRENT_TIMESTAMP,
            finished_at = CURRENT_TIMESTAMP
        WHERE status IN ('pending', 'running', 'waiting_provider')
          AND run_id IN (
              SELECT run_id FROM ai_agent_runs
              WHERE agent_id = 'agent-coordinator'
                AND status IN ('pending', 'running', 'paused', 'waiting_external', 'cancelling')
          )
        """
    )
    op.execute(
        """
        UPDATE ai_agent_runs
        SET status = 'cancelled', pending_requirement_json = NULL,
            cancel_requested_at = CURRENT_TIMESTAMP, finished_at = CURRENT_TIMESTAMP,
            error_code = 'AI_SESSION_SCOPE_MIGRATED',
            error_message = '内容助手会话范围升级，旧运行已取消。'
        WHERE agent_id = 'agent-coordinator'
          AND status IN ('pending', 'running', 'paused', 'waiting_external', 'cancelling')
        """
    )
    op.execute(
        """
        UPDATE ai_agent_sessions
        SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE agent_id = 'agent-coordinator' AND deleted_at IS NULL
        """
    )

    with op.batch_alter_table("ai_agent_sessions") as batch:
        batch.add_column(sa.Column("focus_mode", sa.String(length=32), nullable=False, server_default="follow_route"))
        batch.add_column(sa.Column("pinned_project_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("work_scope_mode", sa.String(length=32), nullable=False, server_default="workspace"))
        batch.add_column(sa.Column("allowed_project_ids_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch.add_column(sa.Column("focus_version", sa.Integer(), nullable=False, server_default="0"))
        batch.create_foreign_key("fk_ai_agent_sessions_pinned_project_id_projects", "projects", ["pinned_project_id"], ["id"])
        batch.create_index("ix_ai_agent_sessions_focus_mode", ["focus_mode"])
        batch.create_index("ix_ai_agent_sessions_pinned_project_id", ["pinned_project_id"])
        batch.create_index("ix_ai_agent_sessions_work_scope_mode", ["work_scope_mode"])
        batch.drop_index("ix_ai_agent_sessions_scope_type")
        batch.drop_index("ix_ai_agent_sessions_project_id")
        batch.drop_index("ix_ai_agent_sessions_page_id")
        batch.drop_index("ix_ai_agent_sessions_component_id")
        batch.drop_index("ix_ai_agent_sessions_source")
        batch.drop_column("scope_type")
        batch.drop_column("project_id")
        batch.drop_column("page_id")
        batch.drop_column("component_id")
        batch.drop_column("source")


def downgrade() -> None:
    """恢复旧字段结构；已归档会话与已取消运行不会自动复活。"""

    with op.batch_alter_table("ai_agent_sessions") as batch:
        batch.add_column(sa.Column("scope_type", sa.String(length=32), nullable=False, server_default="workspace"))
        batch.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("page_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("component_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("source", sa.String(length=128), nullable=False, server_default="editor-workspace"))
        batch.create_index("ix_ai_agent_sessions_scope_type", ["scope_type"])
        batch.create_index("ix_ai_agent_sessions_project_id", ["project_id"])
        batch.create_index("ix_ai_agent_sessions_page_id", ["page_id"])
        batch.create_index("ix_ai_agent_sessions_component_id", ["component_id"])
        batch.create_index("ix_ai_agent_sessions_source", ["source"])
        batch.drop_index("ix_ai_agent_sessions_focus_mode")
        batch.drop_index("ix_ai_agent_sessions_pinned_project_id")
        batch.drop_index("ix_ai_agent_sessions_work_scope_mode")
        batch.drop_constraint("fk_ai_agent_sessions_pinned_project_id_projects", type_="foreignkey")
        batch.drop_column("focus_mode")
        batch.drop_column("pinned_project_id")
        batch.drop_column("work_scope_mode")
        batch.drop_column("allowed_project_ids_json")
        batch.drop_column("focus_version")
