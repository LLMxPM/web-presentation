"""文件功能：为外部任务跨Batch续跑交接增加数据库级唯一性保护。

Revision ID: 20260814_0100
Revises: 20260813_0200
Create Date: 2026-08-14 18:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260814_0100"
down_revision: Union[str, Sequence[str], None] = "20260813_0200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """拒绝含活动冲突的数据库，并创建Requirement与Batch交接唯一索引。"""

    connection = op.get_bind()
    checks = (
        (
            "AI_EXTERNAL_ACTIVE_REQUIREMENT_CONFLICT",
            """
            SELECT run_id FROM ai_agent_requirements
            WHERE kind = 'external_job' AND status IN ('pending','resolving')
            GROUP BY run_id HAVING COUNT(*) > 1
            """,
        ),
        (
            "AI_EXTERNAL_RESUMING_BATCH_CONFLICT",
            """
            SELECT run_id FROM ai_agent_external_batches
            WHERE status = 'resuming'
            GROUP BY run_id HAVING COUNT(*) > 1
            """,
        ),
        (
            "AI_EXTERNAL_COLLECTING_PARENT_CONFLICT",
            """
            SELECT run_id FROM ai_agent_external_batches
            WHERE status = 'collecting' AND member_run_id IS NULL
            GROUP BY run_id HAVING COUNT(*) > 1
            """,
        ),
        (
            "AI_EXTERNAL_COLLECTING_MEMBER_CONFLICT",
            """
            SELECT member_run_id FROM ai_agent_external_batches
            WHERE status = 'collecting' AND member_run_id IS NOT NULL
            GROUP BY member_run_id HAVING COUNT(*) > 1
            """,
        ),
    )
    for code, statement in checks:
        if connection.execute(sa.text(statement)).first() is not None:
            raise RuntimeError(code)

    op.create_index(
        "uq_ai_agent_requirements_active_external_run",
        "ai_agent_requirements",
        ["run_id"],
        unique=True,
        sqlite_where=sa.text("kind = 'external_job' AND status IN ('pending','resolving')"),
        postgresql_where=sa.text("kind = 'external_job' AND status IN ('pending','resolving')"),
    )
    op.create_index(
        "uq_ai_external_batches_resuming_run",
        "ai_agent_external_batches",
        ["run_id"],
        unique=True,
        sqlite_where=sa.text("status = 'resuming'"),
        postgresql_where=sa.text("status = 'resuming'"),
    )
    op.create_index(
        "uq_ai_external_batches_collecting_parent",
        "ai_agent_external_batches",
        ["run_id"],
        unique=True,
        sqlite_where=sa.text("status = 'collecting' AND member_run_id IS NULL"),
        postgresql_where=sa.text("status = 'collecting' AND member_run_id IS NULL"),
    )
    op.create_index(
        "uq_ai_external_batches_collecting_member",
        "ai_agent_external_batches",
        ["member_run_id"],
        unique=True,
        sqlite_where=sa.text("status = 'collecting' AND member_run_id IS NOT NULL"),
        postgresql_where=sa.text("status = 'collecting' AND member_run_id IS NOT NULL"),
    )


def downgrade() -> None:
    """移除外部任务交接唯一索引。"""

    op.drop_index("uq_ai_external_batches_collecting_member", table_name="ai_agent_external_batches")
    op.drop_index("uq_ai_external_batches_collecting_parent", table_name="ai_agent_external_batches")
    op.drop_index("uq_ai_external_batches_resuming_run", table_name="ai_agent_external_batches")
    op.drop_index("uq_ai_agent_requirements_active_external_run", table_name="ai_agent_requirements")
