"""add workspace asset description

Revision ID: 20260419_0028
Revises: 20260418_0027
Create Date: 2026-04-19 20:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260419_0028"
down_revision: str | None = "20260418_0027"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _get_existing_columns(table_name: str) -> set[str]:
    """读取当前表已存在的列名，供兼容性迁移判断使用。"""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    """为工作空间资源增加可选描述字段。"""

    if "description" not in _get_existing_columns("workspace_assets"):
        op.add_column("workspace_assets", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    """回滚工作空间资源描述字段。"""

    if "description" in _get_existing_columns("workspace_assets"):
        op.drop_column("workspace_assets", "description")
