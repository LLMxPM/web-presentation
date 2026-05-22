"""文件功能：移除用户级智能体配置版本字段，并兼容已应用旧迁移的数据库。

Revision ID: 20260507_0040
Revises: 20260506_0039
Create Date: 2026-05-07 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260507_0040"
down_revision: str | None = "20260506_0039"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _has_column(table_name: str, column_name: str) -> bool:
    """检查当前数据库表是否包含指定列，兼容已应用旧 0039 的环境。"""

    inspector = sa.inspect(op.get_bind())
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    """删除智能体与工具用户配置表中的无业务版本列。"""

    if _has_column("ai_agent_user_configs", "config_version"):
        with op.batch_alter_table("ai_agent_user_configs") as batch_op:
            batch_op.drop_column("config_version")

    if _has_column("ai_agent_tool_user_configs", "config_version"):
        with op.batch_alter_table("ai_agent_tool_user_configs") as batch_op:
            batch_op.drop_column("config_version")


def downgrade() -> None:
    """回滚时恢复配置版本列，以兼容旧代码。"""

    if not _has_column("ai_agent_tool_user_configs", "config_version"):
        with op.batch_alter_table("ai_agent_tool_user_configs") as batch_op:
            batch_op.add_column(sa.Column("config_version", sa.Integer(), nullable=False, server_default=sa.text("1")))

    if not _has_column("ai_agent_user_configs", "config_version"):
        with op.batch_alter_table("ai_agent_user_configs") as batch_op:
            batch_op.add_column(sa.Column("config_version", sa.Integer(), nullable=False, server_default=sa.text("1")))
