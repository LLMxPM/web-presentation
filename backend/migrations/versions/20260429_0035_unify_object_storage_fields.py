"""统一对象存储字段。

Revision ID: 20260429_0035
Revises: 20260427_0034
Create Date: 2026-04-29 20:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260429_0035"
down_revision: str | None = "20260427_0034"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """把构建产物本地路径字段替换为对象存储 key 字段。"""

    with op.batch_alter_table("project_build_jobs") as batch_op:
        batch_op.add_column(sa.Column("artifact_storage_key", sa.Text(), nullable=True))
        batch_op.drop_column("artifact_archive_path")


def downgrade() -> None:
    """回滚为旧构建产物本地路径字段。"""

    with op.batch_alter_table("project_build_jobs") as batch_op:
        batch_op.add_column(sa.Column("artifact_archive_path", sa.Text(), nullable=True))
        batch_op.drop_column("artifact_storage_key")
