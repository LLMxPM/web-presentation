"""add project build artifact columns

Revision ID: 20260418_0027
Revises: 20260418_0026
Create Date: 2026-04-18 21:45:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260418_0027"
down_revision: str | None = "20260418_0026"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _get_existing_columns(table_name: str) -> set[str]:
    """读取当前表已存在的列名，供兼容性迁移判断使用。"""

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    """仅在目标列不存在时追加列，兼容旧库和全新库。"""

    if column.name not in _get_existing_columns(table_name):
        op.add_column(table_name, column)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    """仅在目标列存在时删除列，避免重复回滚报错。"""

    if column_name in _get_existing_columns(table_name):
        op.drop_column(table_name, column_name)


def upgrade() -> None:
    """为既有 project_build_jobs 表补充构建产物元数据字段。"""

    _add_column_if_missing("project_build_jobs", sa.Column("artifact_archive_path", sa.Text(), nullable=True))
    _add_column_if_missing("project_build_jobs", sa.Column("artifact_download_url", sa.Text(), nullable=True))
    _add_column_if_missing("project_build_jobs", sa.Column("artifact_entry_file", sa.String(length=255), nullable=True))
    _add_column_if_missing("project_build_jobs", sa.Column("artifact_sha256", sa.String(length=128), nullable=True))
    _add_column_if_missing("project_build_jobs", sa.Column("artifact_size_bytes", sa.Integer(), nullable=True))


def downgrade() -> None:
    """回滚 project_build_jobs 的构建产物元数据字段。"""

    _drop_column_if_exists("project_build_jobs", "artifact_size_bytes")
    _drop_column_if_exists("project_build_jobs", "artifact_sha256")
    _drop_column_if_exists("project_build_jobs", "artifact_entry_file")
    _drop_column_if_exists("project_build_jobs", "artifact_download_url")
    _drop_column_if_exists("project_build_jobs", "artifact_archive_path")
