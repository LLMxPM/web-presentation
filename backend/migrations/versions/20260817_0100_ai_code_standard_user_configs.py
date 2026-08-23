"""文件功能：为用户级页面与组件代码规范覆盖创建独立配置表。

Revision ID: 20260817_0100
Revises: 20260814_0100
Create Date: 2026-08-17 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260817_0100"
down_revision: Union[str, Sequence[str], None] = "20260814_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建用户级代码规范整类型覆盖表。"""

    op.create_table(
        "ai_agent_code_standard_user_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.String(length=128), nullable=False),
        sa.Column("standard_type", sa.String(length=32), nullable=False),
        sa.Column("content_override", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "agent_id",
            "standard_type",
            name="uq_ai_agent_code_standard_user_configs_scope",
        ),
    )
    op.create_index(
        op.f("ix_ai_agent_code_standard_user_configs_user_id"),
        "ai_agent_code_standard_user_configs",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_agent_code_standard_user_configs_agent_id"),
        "ai_agent_code_standard_user_configs",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_agent_code_standard_user_configs_standard_type"),
        "ai_agent_code_standard_user_configs",
        ["standard_type"],
        unique=False,
    )


def downgrade() -> None:
    """删除用户级代码规范整类型覆盖表。"""

    op.drop_index(
        op.f("ix_ai_agent_code_standard_user_configs_standard_type"),
        table_name="ai_agent_code_standard_user_configs",
    )
    op.drop_index(
        op.f("ix_ai_agent_code_standard_user_configs_agent_id"),
        table_name="ai_agent_code_standard_user_configs",
    )
    op.drop_index(
        op.f("ix_ai_agent_code_standard_user_configs_user_id"),
        table_name="ai_agent_code_standard_user_configs",
    )
    op.drop_table("ai_agent_code_standard_user_configs")
