"""add ai llm configs and slot bindings

Revision ID: 20260418_0025
Revises: 20260418_0024
Create Date: 2026-04-18 18:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260418_0025"
down_revision: str | None = "20260418_0024"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """新增用户级大模型配置表与固定槽位绑定表。"""

    op.create_table(
        "ai_llm_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("admin_user_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("provider_key", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("thinking_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("advanced_config_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_ai_llm_configs_admin_user_id", "ai_llm_configs", ["admin_user_id"])
    op.create_index("ix_ai_llm_configs_provider_key", "ai_llm_configs", ["provider_key"])
    op.create_index("ix_ai_llm_configs_status", "ai_llm_configs", ["status"])

    op.create_table(
        "ai_llm_slot_bindings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("admin_user_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("slot", sa.String(length=64), nullable=False),
        sa.Column("llm_config_id", sa.Integer(), sa.ForeignKey("ai_llm_configs.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.UniqueConstraint("admin_user_id", "slot", name="uq_ai_llm_slot_bindings_user_slot"),
    )
    op.create_index("ix_ai_llm_slot_bindings_admin_user_id", "ai_llm_slot_bindings", ["admin_user_id"])
    op.create_index("ix_ai_llm_slot_bindings_llm_config_id", "ai_llm_slot_bindings", ["llm_config_id"])


def downgrade() -> None:
    """回滚用户级大模型配置与固定槽位表。"""

    op.drop_index("ix_ai_llm_slot_bindings_llm_config_id", table_name="ai_llm_slot_bindings")
    op.drop_index("ix_ai_llm_slot_bindings_admin_user_id", table_name="ai_llm_slot_bindings")
    op.drop_table("ai_llm_slot_bindings")

    op.drop_index("ix_ai_llm_configs_status", table_name="ai_llm_configs")
    op.drop_index("ix_ai_llm_configs_provider_key", table_name="ai_llm_configs")
    op.drop_index("ix_ai_llm_configs_admin_user_id", table_name="ai_llm_configs")
    op.drop_table("ai_llm_configs")
