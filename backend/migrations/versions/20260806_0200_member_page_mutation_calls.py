"""文件功能：为成员页面任务拆分运行态工具调用 ID 与 deferred 回灌 ID。

Revision ID: 20260806_0200
Revises: 20260806_0100
Create Date: 2026-08-06 02:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_0200"
down_revision: Union[str, Sequence[str], None] = "20260806_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """新增成员归属与原始 deferred ID，并兼容回填历史父运行任务。"""

    with op.batch_alter_table("ai_page_mutation_jobs") as batch:
        batch.add_column(sa.Column("member_run_id", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("deferred_tool_call_id", sa.String(length=255), nullable=True))
        batch.create_foreign_key(
            "fk_ai_page_mutation_jobs_member_run_id_ai_agent_member_runs",
            "ai_agent_member_runs",
            ["member_run_id"],
            ["member_run_id"],
        )
        batch.create_index("ix_ai_page_mutation_jobs_member_run_id", ["member_run_id"])
        batch.create_index("ix_ai_page_mutation_jobs_deferred_tool_call_id", ["deferred_tool_call_id"])
    op.execute("UPDATE ai_page_mutation_jobs SET deferred_tool_call_id = tool_call_id")
    with op.batch_alter_table("ai_page_mutation_jobs") as batch:
        batch.alter_column("deferred_tool_call_id", existing_type=sa.String(length=255), nullable=False)


def downgrade() -> None:
    """移除成员页面任务扩展字段。"""

    with op.batch_alter_table("ai_page_mutation_jobs") as batch:
        batch.drop_index("ix_ai_page_mutation_jobs_deferred_tool_call_id")
        batch.drop_index("ix_ai_page_mutation_jobs_member_run_id")
        batch.drop_constraint(
            "fk_ai_page_mutation_jobs_member_run_id_ai_agent_member_runs",
            type_="foreignkey",
        )
        batch.drop_column("deferred_tool_call_id")
        batch.drop_column("member_run_id")
