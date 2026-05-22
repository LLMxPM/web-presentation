"""文件功能：为智能体后台 run 任务保存完整用户输入，支撑停止回写。

Revision ID: 20260514_0052
Revises: 20260513_0051
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260514_0052"
down_revision: str | None = "20260513_0051"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_column(table_name: str, column_name: str) -> bool:
    """检查表中是否已存在目标列，兼容重复执行与测试库。"""

    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    """增加完整输入 payload 字段。"""

    if not _has_column("ai_agent_run_tasks", "input_payload_json"):
        with op.batch_alter_table("ai_agent_run_tasks") as batch_op:
            batch_op.add_column(sa.Column("input_payload_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    """移除完整输入 payload 字段。"""

    if _has_column("ai_agent_run_tasks", "input_payload_json"):
        with op.batch_alter_table("ai_agent_run_tasks") as batch_op:
            batch_op.drop_column("input_payload_json")
