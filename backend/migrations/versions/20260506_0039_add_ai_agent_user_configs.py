"""文件功能：新增用户级智能体提示词与工具配置表。

Revision ID: 20260506_0039
Revises: 20260506_0038
Create Date: 2026-05-06 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260506_0039"
down_revision: str | None = "20260506_0038"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """创建用户级 Agent 提示词与工具覆盖配置表。"""

    op.create_table(
        "ai_agent_user_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("admin_user_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("prompt_override", sa.Text(), nullable=True),
        sa.Column("prompt_mode", sa.String(length=32), nullable=False, server_default=sa.text("'override'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("admin_user_id", "agent_id", name="uq_ai_agent_user_configs_user_agent"),
    )
    op.create_index("ix_ai_agent_user_configs_admin_user_id", "ai_agent_user_configs", ["admin_user_id"])
    op.create_index("ix_ai_agent_user_configs_agent_id", "ai_agent_user_configs", ["agent_id"])

    op.create_table(
        "ai_agent_tool_user_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("admin_user_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("tool_key", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("description_override", sa.Text(), nullable=True),
        sa.Column("instructions_override", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("admin_user_id", "agent_id", "tool_key", name="uq_ai_agent_tool_user_configs_user_tool"),
    )
    op.create_index("ix_ai_agent_tool_user_configs_admin_user_id", "ai_agent_tool_user_configs", ["admin_user_id"])
    op.create_index("ix_ai_agent_tool_user_configs_agent_id", "ai_agent_tool_user_configs", ["agent_id"])
    op.create_index("ix_ai_agent_tool_user_configs_tool_key", "ai_agent_tool_user_configs", ["tool_key"])


def downgrade() -> None:
    """删除用户级 Agent 提示词与工具覆盖配置表。"""

    op.drop_index("ix_ai_agent_tool_user_configs_tool_key", table_name="ai_agent_tool_user_configs")
    op.drop_index("ix_ai_agent_tool_user_configs_agent_id", table_name="ai_agent_tool_user_configs")
    op.drop_index("ix_ai_agent_tool_user_configs_admin_user_id", table_name="ai_agent_tool_user_configs")
    op.drop_table("ai_agent_tool_user_configs")
    op.drop_index("ix_ai_agent_user_configs_agent_id", table_name="ai_agent_user_configs")
    op.drop_index("ix_ai_agent_user_configs_admin_user_id", table_name="ai_agent_user_configs")
    op.drop_table("ai_agent_user_configs")
