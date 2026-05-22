"""文件功能：为智能体后台 run 任务增加工具滑动授权字段。

Revision ID: 20260514_0053
Revises: 20260514_0052
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260514_0053"
down_revision: str | None = "20260514_0052"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_column(table_name: str, column_name: str) -> bool:
    """检查表中是否已存在目标列，兼容重复执行与测试库。"""

    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    """增加 run 级工具授权 scope 与滑动过期字段。"""

    with op.batch_alter_table("ai_agent_run_tasks") as batch_op:
        if not _has_column("ai_agent_run_tasks", "tool_scopes_json"):
            batch_op.add_column(sa.Column("tool_scopes_json", sa.JSON(), nullable=True))
        if not _has_column("ai_agent_run_tasks", "tool_auth_expires_at"):
            batch_op.add_column(sa.Column("tool_auth_expires_at", sa.DateTime(timezone=True), nullable=True))
        if not _has_column("ai_agent_run_tasks", "tool_auth_max_expires_at"):
            batch_op.add_column(sa.Column("tool_auth_max_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """移除 run 级工具授权字段。"""

    with op.batch_alter_table("ai_agent_run_tasks") as batch_op:
        if _has_column("ai_agent_run_tasks", "tool_auth_max_expires_at"):
            batch_op.drop_column("tool_auth_max_expires_at")
        if _has_column("ai_agent_run_tasks", "tool_auth_expires_at"):
            batch_op.drop_column("tool_auth_expires_at")
        if _has_column("ai_agent_run_tasks", "tool_scopes_json"):
            batch_op.drop_column("tool_scopes_json")
